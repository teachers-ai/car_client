import os
import io
import numpy as np
from PIL import Image
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.applications import VGG16
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Dense, GlobalAveragePooling2D, Dropout
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.preprocessing.image import ImageDataGenerator
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
        self.class_names = ['Forward', 'Backward', 'Left', 'Right']
        self.img_size = (224, 224)

        # Create models directory
        os.makedirs('models', exist_ok=True)

    def build_model(self):
        """Build VGG16-based model for direction classification"""
        # Load pre-trained VGG16 without top layers
        base_model = VGG16(weights='imagenet', include_top=False, input_shape=(224, 224, 3))

        # Freeze base model layers
        for layer in base_model.layers:
            layer.trainable = False

        # Add custom top layers
        x = base_model.output
        x = GlobalAveragePooling2D()(x)
        x = Dense(512, activation='relu')(x)
        x = Dropout(0.5)(x)
        x = Dense(256, activation='relu')(x)
        x = Dropout(0.3)(x)
        predictions = Dense(4, activation='softmax')(x)  # 4 directions

        # Create final model
        self.model = Model(inputs=base_model.input, outputs=predictions)

        # Compile model
        self.model.compile(
            optimizer=Adam(learning_rate=0.0001),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )

        logger.info('VGG16 model built successfully')
        return self.model

    def load_images_from_folders(self, base_dir='captured_images'):
        """Load images from label-specific folders"""
        images = []
        labels = []

        for label_idx, label_name in enumerate(self.class_names):
            label_dir = os.path.join(base_dir, label_name)

            if not os.path.exists(label_dir):
                logger.warning(f'Directory not found: {label_dir}')
                continue

            image_files = [f for f in os.listdir(label_dir) if f.endswith('.jpg')]

            logger.info(f'Loading {len(image_files)} images from {label_name}')

            for img_file in image_files:
                img_path = os.path.join(label_dir, img_file)
                try:
                    # Load and preprocess image
                    img = Image.open(img_path).convert('RGB')
                    img = img.resize(self.img_size)
                    img_array = np.array(img) / 255.0  # Normalize to 0-1

                    images.append(img_array)

                    # One-hot encode label
                    label = np.zeros(4)
                    label[label_idx] = 1
                    labels.append(label)

                except Exception as e:
                    logger.error(f'Error loading image {img_path}: {e}')
                    continue

        return np.array(images), np.array(labels)

    def train(self, epochs=10, batch_size=32, validation_split=0.2):
        """Train the model on captured images"""
        logger.info('Starting model training...')

        # Load images
        X, y = self.load_images_from_folders()

        if len(X) == 0:
            raise ValueError('No training images found!')

        logger.info(f'Loaded {len(X)} images')

        # Count samples per class
        class_counts = {}
        for idx, class_name in enumerate(self.class_names):
            count = np.sum(np.argmax(y, axis=1) == idx)
            class_counts[class_name] = int(count)

        logger.info(f'Class distribution: {class_counts}')

        # Split data
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=validation_split, random_state=42, stratify=np.argmax(y, axis=1)
        )

        logger.info(f'Training samples: {len(X_train)}, Validation samples: {len(X_val)}')

        # Build model if not exists
        if self.model is None:
            self.build_model()

        # Data augmentation
        datagen = ImageDataGenerator(
            rotation_range=10,
            width_shift_range=0.1,
            height_shift_range=0.1,
            horizontal_flip=True,
            zoom_range=0.1
        )

        # Train model
        history = self.model.fit(
            datagen.flow(X_train, y_train, batch_size=batch_size),
            validation_data=(X_val, y_val),
            epochs=epochs,
            verbose=1
        )

        # Save model
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
        """Predict direction from image"""
        if self.model is None:
            if not self.load_model():
                raise ValueError('Model not loaded!')

        # Preprocess image
        if isinstance(image, bytes):
            img = Image.open(io.BytesIO(image)).convert('RGB')
        else:
            img = Image.fromarray(image).convert('RGB')

        img = img.resize(self.img_size)
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
                for i in range(4)
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
