import os
import io
import numpy as np
from PIL import Image
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Conv2D, MaxPool2D, Flatten
from tensorflow.keras.optimizers import Adam
from sklearn.model_selection import train_test_split
import json
import logging

logger = logging.getLogger(__name__)

class DirectionModel:
    def __init__(self, model_name='direction_model'):
        self.model_name = model_name
        self.model_path = f'models/{model_name}.h5'
        self.history_path = f'models/{model_name}_history.json'
        self.model = None
        # Match notebook: only 3 classes (Left, Forward, Right - no Backward)
        self.class_names = ['Left', 'Forward', 'Right']
        # Match notebook: 200x50 image size (width x height)
        self.img_size = (200, 50)

        # Create models directory
        os.makedirs('models', exist_ok=True)

    def build_model(self):
        """Build CNN model matching the notebook architecture"""
        model = Sequential()
        # Input shape is (height, width, channels) = (50, 200, 3)
        model.add(Conv2D(input_shape=(50, 200, 3), filters=32, kernel_size=(3,3), padding="same", activation="relu"))
        model.add(Conv2D(filters=16, kernel_size=(3,3), padding="same", activation="relu"))
        model.add(MaxPool2D(pool_size=(2,2), strides=(2,2)))
        model.add(Flatten())
        model.add(Dense(units=250, activation="relu"))
        model.add(Dense(units=100, activation="relu"))
        model.add(Dense(units=3, activation="softmax"))  # 3 classes: L, F, R

        # Compile model with Adam optimizer (lr=0.001 as per notebook)
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )

        self.model = model
        logger.info('CNN model built successfully (200x50 input, 3 classes)')
        self.model.summary()
        return self.model

    def load_images_from_folders(self, base_dir='captured_images'):
        """Load images from label-specific folders"""
        images = []
        labels = []

        # Map class names to label indices (matching notebook encoding)
        # Left: [1,0,0], Forward: [0,1,0], Right: [0,0,1]
        label_map = {
            'Left': [1, 0, 0],
            'Forward': [0, 1, 0],
            'Right': [0, 0, 1]
        }

        for class_name in self.class_names:
            label_dir = os.path.join(base_dir, class_name)

            if not os.path.exists(label_dir):
                logger.warning(f'Directory not found: {label_dir}')
                continue

            image_files = [f for f in os.listdir(label_dir) if f.endswith('.jpg')]

            logger.info(f'Loading {len(image_files)} images from {class_name}')

            for img_file in image_files:
                img_path = os.path.join(label_dir, img_file)
                try:
                    # Load and preprocess image
                    img = Image.open(img_path).convert('RGB')
                    img = img.resize(self.img_size)  # Resize to 200x50
                    img_array = np.array(img) / 255.0  # Normalize to 0-1

                    images.append(img_array)
                    labels.append(label_map[class_name])

                except Exception as e:
                    logger.error(f'Error loading image {img_path}: {e}')
                    continue

        return np.array(images), np.array(labels)

    def train(self, epochs=10, batch_size=16, validation_split=0.2, progress_callback=None):
        """Train the model on captured images (matching notebook settings)"""
        logger.info('Starting model training...')

        # Load images
        X, y = self.load_images_from_folders()

        if len(X) == 0:
            raise ValueError('No training images found!')

        logger.info(f'Loaded {len(X)} images with shape {X.shape}')

        # Count samples per class
        class_counts = {}
        for idx, class_name in enumerate(self.class_names):
            count = np.sum(y[:, idx] == 1)
            class_counts[class_name] = int(count)

        logger.info(f'Class distribution: {class_counts}')

        # Split data (80/20 split as per notebook)
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=validation_split, random_state=42
        )

        logger.info(f'Training samples: {len(X_train)}, Validation samples: {len(X_val)}')

        # Always rebuild model to avoid optimizer variable conflicts
        self.build_model()

        # Prepare callbacks
        callbacks = []
        if progress_callback is not None:
            callbacks.append(progress_callback)

        # Train model (no data augmentation, matching notebook)
        history = self.model.fit(
            X_train, y_train,
            batch_size=batch_size,
            epochs=epochs,
            validation_data=(X_val, y_val),
            callbacks=callbacks,
            verbose=1
        )

        # Save model as .h5 file (matching notebook)
        self.model.save(self.model_path)
        logger.info(f'Model saved to {self.model_path}')

        # Save training history
        history_dict = {
            'model_name': self.model_name,
            'loss': [float(x) for x in history.history['loss']],
            'accuracy': [float(x) for x in history.history['accuracy']],
            'val_loss': [float(x) for x in history.history['val_loss']],
            'val_accuracy': [float(x) for x in history.history['val_accuracy']],
            'class_counts': class_counts
        }

        with open(self.history_path, 'w') as f:
            json.dump(history_dict, f, indent=2)

        return history_dict

    def load_model(self):
        """Load pre-trained model"""
        if os.path.exists(self.model_path):
            self.model = keras.models.load_model(self.model_path)
            logger.info(f'Model loaded from {self.model_path}')
            return True
        else:
            logger.warning(f'Model file not found: {self.model_path}')
            return False

    def predict(self, image):
        """Predict direction from image (using bottom half only)"""
        if self.model is None:
            if not self.load_model():
                raise ValueError('Model not loaded!')

        # Preprocess image
        if isinstance(image, bytes):
            img = Image.open(io.BytesIO(image)).convert('RGB')
        else:
            img = Image.fromarray(image).convert('RGB')

        # Crop to bottom half (same as training data)
        width, height = img.size
        img = img.crop((0, height // 2, width, height))

        img = img.resize(self.img_size)  # Resize to 200x50
        img_array = np.array(img) / 255.0
        img_array = np.expand_dims(img_array, axis=0)  # Add batch dimension

        # Predict
        predictions = self.model.predict(img_array, verbose=0)
        predicted_class = np.argmax(predictions[0])
        confidence = float(predictions[0][predicted_class])

        return {
            'direction': self.class_names[predicted_class],
            'confidence': confidence,
            'probabilities': {
                self.class_names[i]: float(predictions[0][i])
                for i in range(3)
            }
        }

    def evaluate(self):
        """Evaluate model on validation data"""
        X, y = self.load_images_from_folders()

        if len(X) == 0:
            raise ValueError('No images found for evaluation!')

        if self.model is None:
            if not self.load_model():
                raise ValueError('Model not loaded!')

        # Evaluate
        loss, accuracy = self.model.evaluate(X, y, verbose=0)

        return {
            'loss': float(loss),
            'accuracy': float(accuracy)
        }
