from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

model_name = "pszemraj/grammar-synthesis-small"
print(f"Downloading model: {model_name}...")
AutoTokenizer.from_pretrained(model_name)
AutoModelForSeq2SeqLM.from_pretrained(model_name)
print("Model downloaded successfully.")
