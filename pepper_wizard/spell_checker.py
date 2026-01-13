from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

class SpellChecker:
    """
    A context-aware spell checker using a T5-Small model fine-tuned for grammar correction.
    Model: pszemraj/grammar-synthesis-small
    """
    def __init__(self, model_name="pszemraj/grammar-synthesis-small"):
        print(f"Loading SpellChecker model: {model_name}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.model.to(self.device)
        print(f"SpellChecker loaded on {self.device}.")

    def correct_sentence(self, sentence):
        """
        Corrects grammar and spelling in a given sentence.
        """
        if not sentence:
            return ""


        input_text = f"grammar: {sentence}"
        tokenized_input = self.tokenizer(input_text, return_tensors="pt").to(self.device)

        # Generate correction
        with torch.no_grad():
            outputs = self.model.generate(
                **tokenized_input,
                max_length=512,
                num_beams=2, # Beam search for better quality
                early_stopping=True
            )
        
        corrected_sentence = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Post-processing to clean up model artifacts
        if corrected_sentence.lower().startswith("grammar:"):
            corrected_sentence = corrected_sentence[8:].strip()
        elif corrected_sentence.lower().startswith("grammar test :"):
             corrected_sentence = corrected_sentence[14:].strip()
             
        return corrected_sentence
