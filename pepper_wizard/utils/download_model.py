from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

def download_model():
    model_name = "vennify/t5-base-grammar-correction"
    print(f"Downloading model: {model_name}...")
    AutoTokenizer.from_pretrained(model_name)
    AutoModelForSeq2SeqLM.from_pretrained(model_name)
    print("Download complete.")

if __name__ == "__main__":
    download_model()
