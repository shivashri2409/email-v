# -*- coding: utf-8 -*-
"""Untitled0.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1hrB-fStSAUWp74u2uh3A2tvltvm8hNs4
"""

!pip install fastapi
!pip install datasets==2.13.0
!pip install slowapi
!pip install openpyxl
!pip install pyngrok
!pip install --upgrade torch datasets
!pip install torchvision
!pip install --upgrade transformers
!pip install uvicorn

from google.colab import drive
drive.mount('/content/drive')
import os
import uvicorn

import io
import os
import re
import spacy
import pandas as pd
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import torch
from typing import Dict, List, Optional, Tuple  # Import Tuple
import pandas as pd
from datasets import Dataset
from transformers import (
    DistilBertForSequenceClassification,
    DistilBertTokenizer,
    Trainer,
    TrainingArguments
)
from sklearn.model_selection import train_test_split
from datasets import Dataset
import numpy as np
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler  # Import _rate_limit_exceeded_handler instead of SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded  # Import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

import transformers

!pip install --upgrade transformers==4.16.0

from google.colab import files

# Upload the file
uploaded = files.upload()

# Initialize components
!python -m spacy download en_core_web_sm
nlp = spacy.load("en_core_web_sm")

# For Google Colab, we'll use ngrok to expose the FastAPI server
from pyngrok import ngrok
import nest_asyncio
from fastapi.middleware.cors import CORSMiddleware

# Configuration
CONFIG = {
    "file_path": '/content/drive/My Drive/email.csv',  # Update with your dataset path
    "model_save_path": "models/email_classifier",
    "test_size": 0.2,
    "random_state": 42
}

# Directly load the dataset
new_var = '/content/drive/My Drive/email.csv'
file_path = new_var
try:
    df = pd.read_csv(file_path)
    print("Dataset loaded successfully!")
    print(df.head())  # Display the first few rows of the dataframe
except FileNotFoundError:
    print(f"File not found at {file_path}")
except Exception as e:
    print(f"Error occurred: {e}")

# Load and preprocess dataset
def load_and_preprocess_data() -> Optional[pd.DataFrame]:
    try:
        # In Colab, you'll need to upload the file first

        df = pd.read_csv(next(iter(uploaded.keys())))

        # Basic validation - adjust column names to match your dataset
        if 'email' not in df.columns or 'type' not in df.columns:
            raise ValueError("Dataset must contain 'email' and 'type' columns")
            # Clean data
        df = df.dropna(subset=["email"])
        df = df.rename(columns={"email": "email_text", "type": "category"})
        df["category"] = df["category"].astype(str)  # Convert to string

        return df
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return None

# Load and check the dataset
df = pd.read_csv("/content/drive/My Drive/email.csv")

# Check the column names
print(df.columns)

# Print the first few rows to inspect the data
print(df.head())

# Check for missing values in the 'type' column
print(df['type'].isnull().sum())

# If there are missing values, fill them
df['type'] = df['type'].fillna('Unknown')

# Convert 'type' column to categorical
df['type'] = df['type'].astype('category')

# Now continue with the rest of the process

def initialize_model(df: pd.DataFrame) -> pd.DataFrame:
    global CLASS_LABELS, tokenizer, model

    # Convert 'category' column to categorical dtype explicitly
    df["category"] = df["category"].astype("category")

    # Get class labels from dataset
    CLASS_LABELS = df["category"].cat.categories.tolist()
    num_labels = len(CLASS_LABELS)

    # Initialize tokenizer and model
    tokenizer = DistilBertTokenizer.from_pretrained("distilbert-base-uncased")
    model = DistilBertForSequenceClassification.from_pretrained(
        "distilbert-base-uncased",
        num_labels=num_labels
    )

    # Convert labels to numerical values
    df["label"] = df["category"].cat.codes

    return df

# Dataset preparation for training
def prepare_datasets(df: pd.DataFrame) -> Tuple[Dataset, Dataset]:
    # Split data
    train_df, val_df = train_test_split(
        df,
        test_size=CONFIG["test_size"],
        random_state=CONFIG["random_state"],
        stratify=df["label"]
    )

    # Create Hugging Face datasets
    train_dataset = Dataset.from_pandas(train_df)
    val_dataset = Dataset.from_pandas(val_df)

    # Tokenization function
    def tokenize_function(examples):
        return tokenizer(
            examples["email_text"],
            padding="max_length",
            truncation=True,
            max_length=512
        )

# Tokenize datasets
def tokenize_datasets(train_dataset, val_dataset, tokenizer):
    def tokenize_function(examples):
        return tokenizer(
            examples["email"],
            padding="max_length",
            truncation=True,
            max_length=512
        )

    tokenized_train = train_dataset.map(tokenize_function, batched=True)
    tokenized_val = val_dataset.map(tokenize_function, batched=True)

    return tokenized_train, tokenized_val

# Metrics computation
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    return {"accuracy": (predictions == labels).mean()}

# Model training
def train_model(tokenized_train, tokenized_val):
    training_args = TrainingArguments(
        output_dir=CONFIG["model_save_path"],
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        num_train_epochs=3,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        logging_dir='./logs',
        logging_steps=10,
        load_best_model_at_end=True
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_val,
        compute_metrics=compute_metrics
    )

    trainer.train()
    trainer.save_model(CONFIG["model_save_path"])

    return trainer

# PII Patterns
PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
    "credit_card": r'\b(?:\d[ -]*?){13,16}\b',
    "ssn": r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
    "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
}

# PII Masking functions
def validate_credit_card(number: str) -> bool:
    """Validate credit card number using Luhn algorithm"""
    number = re.sub(r'[^0-9]', '', number)
    if len(number) < 13 or len(number) > 19:
        return False

    total = 0
    reverse_digits = number[::-1]
    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n = (n // 10) + (n % 10)
        total += n
    return total % 10 == 0

def mask_pii(text: str) -> Dict:
    """Mask PII in text and return details of masked entities"""
    masked_text = text
    masked_entities = []

    # Process each PII type
    for pii_type, pattern in PII_PATTERNS.items():
        for match in re.finditer(pattern, text):
            original_value = match.group()

            # Special validation for credit cards
            if pii_type == "credit_card" and not validate_credit_card(original_value):
                continue

            # Create masked version
            if pii_type == "email":
                masked_value = "[EMAIL_REDACTED]"
            elif pii_type == "phone":
                masked_value = "[PHONE_REDACTED]"
            elif pii_type == "credit_card":
                masked_value = "[CREDIT_CARD_REDACTED]"
            elif pii_type == "ssn":
                masked_value = "[SSN_REDACTED]"
            elif pii_type == "ip_address":
                masked_value = "[IP_REDACTED]"
            else:
                masked_value = f"[{pii_type.upper()}_REDACTED]"

            # Replace in text
            masked_text = masked_text.replace(original_value, masked_value)

            # Record the masked entity
            masked_entities.append({
                "type": pii_type,
                "original_value": original_value,
                "masked_value": masked_value,
                "start_pos": match.start(),
                "end_pos": match.end()
            })

    return {
        "masked_text": masked_text,
        "masked_entities": masked_entities
    }

# Classification function
def classify_email(text: str) -> str:
    """Classify email text into one of the predefined categories"""
    if not CLASS_LABELS or not tokenizer or not model:
        raise RuntimeError("Model not initialized")

    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
    with torch.no_grad():
        outputs = model(**inputs)
    predicted_class = torch.argmax(outputs.logits, dim=1).item()
    return CLASS_LABELS[predicted_class]

# Initialize FastAPI app with CORS
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# API Models
class EmailRequest(BaseModel):
    email_body: str

class EmailResponse(BaseModel):
    input_email_body: str
    list_of_masked_entities: List[Dict]
    masked_email: str
    category_of_the_email: str

# API Endpoints
@app.post("/process_email", response_model=EmailResponse)
async def process_email(email_request: EmailRequest):
    try:
        # Mask PII
        masking_result = mask_pii(email_request.email_body)

        # Classify email
        category = classify_email(email_request.email_body)

        return EmailResponse(
            input_email_body=email_request.email_body,
            list_of_masked_entities=masking_result["masked_entities"],
            masked_email=masking_result["masked_text"],
            category_of_the_email=category
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "model_initialized": model is not None,
        "categories": CLASS_LABELS if CLASS_LABELS else None
    }

# Initialize system
def initialize_system():
    global trainer

    print("Loading dataset...")
    df = load_and_preprocess_data()
    if df is None:
        raise RuntimeError("Failed to load dataset")

    print("Initializing model...")
    df = initialize_model(df)

    print("Preparing datasets...")
    train_set, val_set = prepare_datasets(df)

    print("Training model...")
    trainer = train_model(train_set, val_set)
    print("Training complete!")

    return trainer

import os

# Check if the file exists in the specified path
file_path = '/content/drive/My Drive/email.csv'
print("File exists?", os.path.exists(file_path))

# List the contents of the folder to confirm the file
print("Contents of 'My Drive':")
print(os.listdir('/content/drive/My Drive'))

# Main execution for Colab
if __name__ == "__main__":
    # Install required packages
    !pip install --upgrade transformers
    !pip install -q torch transformers datasets fastapi uvicorn pyngrok nest_asyncio spacy
    import wandb
    wandb.login(key="f7b15fdaa8dd5293f262566dc41a86f2fca37384")  # <-- Put your key here


    # Initialize the system
    try:
        print("Loading dataset...")
        df = load_and_preprocess_data()
        if df is None:
            raise RuntimeError("Failed to load dataset")

        print("Initializing model...")
        df = initialize_model(df)

        print("Preparing datasets...")
        # Convert to dictionary format first
        train_df, val_df = train_test_split(
            df,
            test_size=CONFIG["test_size"],
            random_state=CONFIG["random_state"],
            stratify=df["label"]
        )

        # Convert to Hugging Face datasets
        train_dataset = Dataset.from_dict({
            "text": train_df["email_text"].tolist(),
            "label": train_df["label"].tolist()
        })
        val_dataset = Dataset.from_dict({
            "text": val_df["email_text"].tolist(),
            "label": val_df["label"].tolist()
        })

        # Tokenization function
        def tokenize_function(examples):
            return tokenizer(
                examples["text"],
                padding="max_length",
                truncation=True,
                max_length=512
            )

        # Tokenize datasets
        tokenized_train = train_dataset.map(tokenize_function, batched=True)
        tokenized_val = val_dataset.map(tokenize_function, batched=True)

        print("Training model...")
        training_args = TrainingArguments(
            output_dir=CONFIG["model_save_path"],
            per_device_train_batch_size=8,
            per_device_eval_batch_size=8,
            num_train_epochs=3,
            eval_strategy="epoch",
            save_strategy="epoch",
            logging_dir='./logs',
            logging_steps=10,
            load_best_model_at_end=True
        )

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_train,
            eval_dataset=tokenized_val,
            compute_metrics=compute_metrics
        )

        trainer.train()
        trainer.save_model(CONFIG["model_save_path"])
        print("Training complete!")

    except Exception as e:
        print(f"Initialization failed: {e}")
        raise

    # Set up ngrok tunnel
    from pyngrok import ngrok
    import nest_asyncio
    ngrok.set_auth_token("2w7HNrwwwFepBUGBcGCcDjqvdRe_JTrdZTvueTbSuxFj72T9")
    # 2. Create tunnel with custom subdomain (optional)

# Create tunnel
ngrok_tunnel = ngrok.connect(8000)  # ← No extra indentation here
public_url = ngrok_tunnel.public_url  # ← Aligned with ngrok_tunnel assignment
print('Public URL:', public_url)

!pip install fastapi uvicorn nest_asyncio pyngrok

from fastapi import FastAPI
import nest_asyncio
from pyngrok import ngrok
import uvicorn
import threading

# Create FastAPI app
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

# Allow async in Colab
nest_asyncio.apply()

# Start ngrok tunnel in background
def start_ngrok():
    public_url = ngrok.connect(8000)
    print(f"Public URL: {public_url}")

ngrok_thread = threading.Thread(target=start_ngrok, daemon=True)
ngrok_thread.start()

# Run FastAPI server
uvicorn.run(app, host="0.0.0.0", port=8000)