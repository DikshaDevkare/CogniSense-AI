"""AegisMind dual-stream decision engine.
Vision and typing streams are fused only when their data is available.
"""
import math
import time

from config import Config


class DualStreamDecisionEngine:
    def __init__(self):
        self.cfi = 0.0
        self.last_cfi_time = None
        self.overload_since = None
        self.last_state = 'NORMAL_STATE'
        self.last_result = None

    @staticmethod
    def _clamp(value, lo=0.0, hi=100.0):
        return max(lo, min(hi, float(value)))

    def _update_cfi(self, cli, now):
        if self.last_cfi_time is None:
            self.cfi = self._clamp(cli)
        else:
            dt = max(0.0, now - self.last_cfi_time)
            decay = math.exp(-Config.CFI_LAMBDA * dt)
            self.cfi = Config.CFI_ALPHA * self._clamp(cli) + (1 - Config.CFI_ALPHA) * self.cfi * decay
        self.last_cfi_time = now
        return round(self._clamp(self.cfi), 1)

    def decide(self, vision, typing=None, now=None):
        now = float(now or time.time())
        typing = typing or {}

        cli = vision.get('cli_vision')
        face_ok = bool(vision.get('face_detected', False)) and cli is not None
        if not face_ok:
            # Do not fabricate missing vision values. Preserve fatigue state with decay only.
            cfi = self._update_cfi(0.0, now) if self.last_cfi_time is not None else 0.0
            return self._build(vision, typing, 'NORMAL_STATE', cfi, [], False)

        kpm = typing.get('kpm')
        bsr = typing.get('backspace_ratio')
        pause = typing.get('pause_duration')
        typing_available = bool(typing.get('available')) and kpm is not None

        reasons = []
        if cli >= Config.CLI_FLOW_MAX:
            reasons.append(f'Vision CLI = {cli:.1f}')
        elif cli >= Config.CLI_NORMAL_MAX:
            reasons.append(f'Vision CLI = {cli:.1f}')

        if typing_available:
            if bsr is not None and bsr > Config.OVERLOAD_BSR_MIN:
                reasons.append(f'Backspace ratio = {bsr:.2f}')
            if pause is not None and pause > Config.OVERLOAD_PAUSE_SECS:
                reasons.append(f'Pause duration = {pause:.1f} sec')

        overload_condition = cli >= Config.CLI_FLOW_MAX and typing_available and (
            (bsr is not None and bsr > Config.OVERLOAD_BSR_MIN) or
            (pause is not None and pause > Config.OVERLOAD_PAUSE_SECS)
        )

        flow_condition = cli >= Config.CLI_NORMAL_MAX and cli < Config.CLI_FLOW_MAX
        if typing_available:
            flow_condition = flow_condition and kpm >= Config.FLOW_KPM_MIN and (bsr is None or bsr <= Config.FLOW_BSR_MAX) and (pause is None or pause <= Config.OVERLOAD_PAUSE_SECS)

        if overload_condition:
            if self.overload_since is None:
                self.overload_since = now
            sustained = now - self.overload_since
            if sustained > Config.OVERLOAD_SUSTAINED_SECS:
                state = 'COGNITIVE_OVERLOAD'
                reasons.append(f'Sustained for = {sustained:.1f} sec')
            else:
                state = self.last_state if self.last_state != 'COGNITIVE_OVERLOAD' else 'NORMAL_STATE'
        else:
            self.overload_since = None
            state = 'FLOW_STATE' if flow_condition else 'NORMAL_STATE'

        cfi = self._update_cfi(cli, now)
        if cfi >= Config.CFI_ALERT:
            reasons.append('High cumulative cognitive strain detected')

        self.last_state = state
        return self._build(vision, typing, state, cfi, reasons, True)

    def _build(self, vision, typing, state, cfi, reasons, vision_available):
        focus = vision.get('focus_score', 0)
        stress = vision.get('stress', 0)
        if state == 'COGNITIVE_OVERLOAD':
            focus = min(focus, max(0, 100 - int(cfi * 0.35)))
            stress = max(stress, min(100, int(cfi * 0.75)))
        elif state == 'FLOW_STATE':
            focus = max(focus, 70)

        remediation = []
        if state == 'COGNITIVE_OVERLOAD':
            remediation = [
                'Pause for 2 minutes and breathe.',
                'Break the task into one small step.',
                'Resume after your attention stabilizes.'
            ]
        elif cfi >= Config.CFI_ALERT:
            remediation = ['High cumulative cognitive strain detected. A short break is recommended.']

        return {
            **vision,
            'state': state,
            'focus_score': int(self._clamp(focus)),
            'stress': int(self._clamp(stress)),
            'cfi': cfi,
            'typing_available': bool(typing.get('available')),
            'kpm': typing.get('kpm'),
            'backspace_ratio': typing.get('backspace_ratio'),
            'pause_duration': typing.get('pause_duration'),
            'keypress_count': typing.get('keypress_count', 0),
            'backspace_count': typing.get('backspace_count', 0),
            'reasons': reasons,
            'remediation': remediation,
            'vision_available': vision_available,
        }


_engines = {}


def get_engine(user_id=1):
    user_id = int(user_id)
    if user_id not in _engines:
        _engines[user_id] = DualStreamDecisionEngine()
    return _engines[user_id]


def reset_engine(user_id=1):
    _engines[int(user_id)] = DualStreamDecisionEngine()
