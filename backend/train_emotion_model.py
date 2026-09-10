# ============================================================
# train_emotion_model.py  — IMAGE FOLDER VERSION
# Reads from train/ and test/ folders directly
# Emotions: angry, happy, sad, neutral (4 classes)
#
# Dataset structure expected:
#   backend/dataset/train/angry/  *.jpg/*.png
#   backend/dataset/train/happy/
#   backend/dataset/train/sad/
#   backend/dataset/train/neutral/
#   backend/dataset/test/angry/
#   ...
#
# RUN: python train_emotion_model.py
# ============================================================

import os
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import tensorflow as tf
from tensorflow import keras
from keras import layers, models, callbacks, regularizers

# ========================
# CONFIG
# ========================
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, 'dataset')
TRAIN_DIR   = os.path.join(DATASET_DIR, 'train')
TEST_DIR    = os.path.join(DATASET_DIR, 'test')
MODEL_PATH  = os.path.join(BASE_DIR, 'emotion_model.h5')

IMG_SIZE    = 48
BATCH_SIZE  = 128
EPOCHS      = 15

# Sirf ye 4 emotions use karenge
TARGET_EMOTIONS = ['angry', 'happy', 'sad', 'neutral']
NUM_CLASSES     = len(TARGET_EMOTIONS)

print("\n" + "="*52)
print("  CogniSense AI — Emotion Model Training")
print("  Image Folders → CNN → emotion_model.h5")
print("="*52 + "\n")

# ========================
# CHECK FOLDERS
# ========================
def check_dataset():
    if not os.path.exists(TRAIN_DIR):
        print(f"❌ train/ folder not found at: {TRAIN_DIR}")
        print("   Copy your dataset train/ folder to backend/dataset/train/")
        sys.exit(1)

    found = []
    for emo in TARGET_EMOTIONS:
        p = os.path.join(TRAIN_DIR, emo)
        if os.path.exists(p):
            count = len([f for f in os.listdir(p)
                         if f.lower().endswith(('.jpg','.jpeg','.png'))])
            found.append((emo, count))
            print(f"  ✅ {emo:10s} — {count} images")
        else:
            print(f"  ⚠️  {emo:10s} — folder not found (will skip)")

    if not found:
        print("\n❌ No emotion folders found!")
        sys.exit(1)

    print(f"\n✅ Found {len(found)} emotion classes")
    return [e for e,_ in found]

# ========================
# DATA LOADER
# ========================
def load_images_from_folder(base_dir, emotion_list):
    """Load images from emotion subfolders, convert to grayscale 48x48."""
    import cv2
    X, y = [], []
    for idx, emotion in enumerate(emotion_list):
        folder = os.path.join(base_dir, emotion)
        if not os.path.exists(folder):
            continue
        files = [f for f in os.listdir(folder)
                 if f.lower().endswith(('.jpg','.jpeg','.png'))]
        print(f"  Loading {emotion}: {len(files)} images...")
        for fname in files:
            fpath = os.path.join(folder, fname)
            try:
                img = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                img = cv2.resize(img, (IMG_SIZE, IMG_SIZE))
                X.append(img)
                y.append(idx)
            except Exception:
                continue

    X = np.array(X, dtype=np.float32) / 255.0
    X = X.reshape(-1, IMG_SIZE, IMG_SIZE, 1)
    y = np.array(y, dtype=np.int32)
    return X, y

# ========================
# CNN MODEL
# ========================
def build_model(num_classes):
    model = models.Sequential([
        layers.Input(shape=(IMG_SIZE, IMG_SIZE, 1)),

        # Block 1
        layers.Conv2D(64, (3,3), padding='same', activation='relu',
                      kernel_regularizer=regularizers.l2(1e-4)),
        layers.BatchNormalization(),
        layers.Conv2D(64, (3,3), padding='same', activation='relu'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(2,2),
        layers.Dropout(0.25),

        # Block 2
        layers.Conv2D(128, (3,3), padding='same', activation='relu',
                      kernel_regularizer=regularizers.l2(1e-4)),
        layers.BatchNormalization(),
        layers.Conv2D(128, (3,3), padding='same', activation='relu'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(2,2),
        layers.Dropout(0.25),

        # Block 3
        layers.Conv2D(256, (3,3), padding='same', activation='relu',
                      kernel_regularizer=regularizers.l2(1e-4)),
        layers.BatchNormalization(),
        layers.Conv2D(256, (3,3), padding='same', activation='relu'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(2,2),
        layers.Dropout(0.40),

        # Classifier
        layers.Flatten(),
        layers.Dense(512, activation='relu',
                     kernel_regularizer=regularizers.l2(1e-4)),
        layers.BatchNormalization(),
        layers.Dropout(0.50),
        layers.Dense(256, activation='relu'),
        layers.Dropout(0.30),
        layers.Dense(num_classes, activation='softmax'),
    ], name='CogniSense_EmotionCNN')

    return model

# ========================
# AUGMENTATION
# ========================
def build_augmentation():
    return keras.Sequential([
        layers.RandomFlip('horizontal'),
        layers.RandomRotation(0.10),
        layers.RandomZoom(0.10),
        layers.RandomContrast(0.10),
    ])

# ========================
# PLOT HISTORY
# ========================
def plot_history(history):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle('CogniSense AI — Training Curves', fontsize=14)

    axes[0].plot(history.history['accuracy'],     label='Train', color='#a855f7')
    axes[0].plot(history.history['val_accuracy'], label='Val',   color='#0ea5e9')
    axes[0].set_title('Accuracy'); axes[0].legend(); axes[0].grid(True, alpha=0.3)

    axes[1].plot(history.history['loss'],     label='Train', color='#ef4444')
    axes[1].plot(history.history['val_loss'], label='Val',   color='#f97316')
    axes[1].set_title('Loss'); axes[1].legend(); axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    out = os.path.join(BASE_DIR, 'training_curves.png')
    plt.savefig(out, dpi=100)
    plt.close()
    print(f"📊 Training curves saved: {out}")

# ========================
# SAVE EMOTION LABELS
# ========================
def save_labels(emotion_list):
    """Save label order so emotion_detector.py uses same mapping."""
    label_path = os.path.join(BASE_DIR, 'emotion_labels.txt')
    with open(label_path, 'w') as f:
        for e in emotion_list:
            f.write(e.capitalize() + '\n')
    print(f"💾 Labels saved: {label_path}")

# ========================
# MAIN TRAIN
# ========================
def train():
    import cv2

    # 1. Check dataset
    print("📂 Checking dataset folders...")
    available_emotions = check_dataset()

    # 2. Load train data
    print(f"\n📥 Loading TRAIN data...")
    X_train, y_train = load_images_from_folder(TRAIN_DIR, available_emotions)
    print(f"  Train shape: {X_train.shape}")

    # 3. Load test data
    print(f"\n📥 Loading TEST data...")
    if os.path.exists(TEST_DIR):
        X_test, y_test = load_images_from_folder(TEST_DIR, available_emotions)
        print(f"  Test shape: {X_test.shape}")
    else:
        # Split from train if no test folder
        split = int(len(X_train) * 0.85)
        X_test,  y_test  = X_train[split:], y_train[split:]
        X_train, y_train = X_train[:split], y_train[:split]
        print(f"  No test/ folder — using 15% of train as test")

    # 4. Validation split from train
    val_split = int(len(X_train) * 0.85)
    X_val,   y_val   = X_train[val_split:], y_train[val_split:]
    X_train, y_train = X_train[:val_split], y_train[:val_split]

    print(f"\n📊 Split — Train:{len(X_train)} | Val:{len(X_val)} | Test:{len(X_test)}")

    num_classes = len(available_emotions)

    # 5. One-hot encode
    y_train_oh = keras.utils.to_categorical(y_train, num_classes)
    y_val_oh   = keras.utils.to_categorical(y_val,   num_classes)
    y_test_oh  = keras.utils.to_categorical(y_test,  num_classes)

    # 6. Build model
    model = build_model(num_classes)
    model.summary()

    # 7. Compile
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )

    # 8. Callbacks
    cb_list = [
        callbacks.EarlyStopping(
            monitor='val_accuracy', patience=8,
            restore_best_weights=True, verbose=1
        ),
        callbacks.ReduceLROnPlateau(
            monitor='val_loss', factor=0.5,
            patience=4, min_lr=1e-6, verbose=1
        ),
        callbacks.ModelCheckpoint(
            MODEL_PATH, monitor='val_accuracy',
            save_best_only=True, verbose=1
        ),
    ]

    # 9. Augmented dataset
    augment  = build_augmentation()
    train_ds = tf.data.Dataset.from_tensor_slices((X_train, y_train_oh))
    train_ds = (train_ds
                .shuffle(2048)
                .batch(BATCH_SIZE)
                .map(lambda x, y: (augment(x, training=True), y),
                     num_parallel_calls=tf.data.AUTOTUNE)
                .prefetch(tf.data.AUTOTUNE))

    val_ds = (tf.data.Dataset.from_tensor_slices((X_val, y_val_oh))
              .batch(BATCH_SIZE)
              .prefetch(tf.data.AUTOTUNE))

    # 10. Train
    print(f"\n🚀 Training started — {EPOCHS} epochs max...\n")
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS,
        callbacks=cb_list,
        verbose=1
    )

    # 11. Evaluate
    print("\n📈 Final evaluation on test set...")
    loss, acc = model.evaluate(X_test, y_test_oh, verbose=0)
    print(f"✅ Test Accuracy : {acc*100:.2f}%")
    print(f"✅ Test Loss     : {loss:.4f}")

    # 12. Save
    model.save(MODEL_PATH)
    save_labels(available_emotions)
    print(f"\n💾 Model saved  : {MODEL_PATH}")

    # 13. Plot
    plot_history(history)

    print("\n🎉 Training complete! emotion_model.h5 is ready.")
    print("   Now run: python app.py")

if __name__ == '__main__':
    train()