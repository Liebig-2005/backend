from fastapi import APIRouter, UploadFile, File, HTTPException
import shutil
import os
import uuid
import base64
import requests

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Gemini API config
GEMINI_API_KEY = "AIzaSyBJ5YKoKcHODszQQoXlQ0Xfy-vZsDBN7yI"
GEMINI_MODEL = "gemini-2.5-flash"  # or another Gemini model that supports image
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)

@router.post("/")
async def scan_leaf(image: UploadFile = File(...)):
    # Validate image
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Generate unique filename & save
    extension = os.path.splitext(image.filename)[1] or ".jpg"
    unique_name = f"{uuid.uuid4()}{extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(image.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving image: {e}")

    # Read file and convert to base64
    with open(file_path, "rb") as f:
        image_bytes = f.read()
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    # First, check if image is plant/farming related
    validation_prompt = """Analyze this image. Is this image related to plants, crops, farming, or agriculture? 
    Respond with only 'YES' if it's plant/farming related, or 'NO' if it's not."""
    
    validation_body = {
        "contents": [
            {
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": image.content_type,
                            "data": b64_data
                        }
                    },
                    {"text": validation_prompt}
                ]
            }
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    try:
        # Check if image is plant-related
        validation_resp = requests.post(GEMINI_API_URL, json=validation_body, headers=headers, timeout=30)
        validation_resp.raise_for_status()
        validation_result = validation_resp.json()
        
        if "candidates" in validation_result and len(validation_result["candidates"]) > 0:
            validation_text = "".join([p.get("text", "") for p in validation_result["candidates"][0]["content"]["parts"] if "text" in p])
            if "NO" in validation_text.upper() or "not" in validation_text.lower():
                raise HTTPException(
                    status_code=400, 
                    detail="This image does not appear to be plant or farming related. Please upload an image of a crop, plant, or leaf."
                )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Validation check failed: {e}")
        # Continue anyway if validation fails

    # Main analysis prompt
    analysis_prompt = """Analyze this crop/plant image for diseases. Provide your response in the following exact format:

DISEASE: [Disease name only - just the name, no description, no story, no explanation. Examples: "Leaf Spot", "Powdery Mildew", "Rust", "Healthy"]
DESCRIPTION: [Brief description of the disease symptoms, appearance, and characteristics]
TREATMENT: [Detailed treatment methods, prevention strategies, and recommended actions]

CRITICAL REQUIREMENTS:
- Disease name must be ONLY the disease name (e.g., "Leaf Spot" not "This appears to be Leaf Spot disease")
- Do NOT include asterisks (*) anywhere in your response
- Do NOT use markdown formatting
- If healthy, disease name should be just "Healthy"
- Keep disease name to maximum 3-4 words"""

    body = {
        "contents": [
            {
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": image.content_type,
                            "data": b64_data
                        }
                    },
                    {"text": analysis_prompt}
                ]
            }
        ]
    }

    try:
        resp = requests.post(GEMINI_API_URL, json=body, headers=headers, timeout=60)
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        print("Gemini API call failed:", e)
        raise HTTPException(status_code=500, detail="AI analysis failed")

    # Parse response
    disease = None
    description = None
    treatment = None

    if "candidates" in result and len(result["candidates"]) > 0:
        parts = result["candidates"][0]["content"]["parts"]
        text_output = "".join([p.get("text", "") for p in parts if "text" in p])
        
        # Remove all asterisks
        text_output = text_output.replace("*", "").strip()
        
        # Parse structured response
        lines = text_output.split("\n")
        current_section = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            if line.startswith("DISEASE:"):
                if current_section == "DESCRIPTION" and current_content:
                    description = " ".join(current_content).strip()
                elif current_section == "TREATMENT" and current_content:
                    treatment = " ".join(current_content).strip()
                current_section = "DISEASE"
                current_content = [line.replace("DISEASE:", "").strip()]
            elif line.startswith("DESCRIPTION:"):
                if current_section == "DISEASE" and current_content:
                    disease = " ".join(current_content).strip()
                elif current_section == "TREATMENT" and current_content:
                    treatment = " ".join(current_content).strip()
                current_section = "DESCRIPTION"
                current_content = [line.replace("DESCRIPTION:", "").strip()]
            elif line.startswith("TREATMENT:"):
                if current_section == "DESCRIPTION" and current_content:
                    description = " ".join(current_content).strip()
                current_section = "TREATMENT"
                current_content = [line.replace("TREATMENT:", "").strip()]
            elif line and current_section:
                current_content.append(line)
        
        # Handle last section
        if current_section == "DISEASE" and current_content:
            disease_text = " ".join(current_content).strip()
            # Extract just the disease name (first line, first sentence, or first few words)
            # Remove common prefixes like "This is", "The disease is", etc.
            disease_text = disease_text.replace("This is", "").replace("The disease is", "").replace("This appears to be", "").strip()
            # Get first line or first sentence, max 4 words
            disease = disease_text.split("\n")[0].split(".")[0].strip()
            # Limit to first 4 words max
            words = disease.split()
            if len(words) > 4:
                disease = " ".join(words[:4])
        elif current_section == "DESCRIPTION" and current_content:
            description = " ".join(current_content).strip()
        elif current_section == "TREATMENT" and current_content:
            treatment = " ".join(current_content).strip()
        
        # Fallback: if parsing failed, try to extract from text
        if not disease or not description or not treatment:
            # Try alternative parsing
            if "DISEASE:" in text_output:
                disease_part = text_output.split("DISEASE:")[1].split("DESCRIPTION:")[0].strip() if "DESCRIPTION:" in text_output else text_output.split("DISEASE:")[1].strip()
                # Clean up and get just the disease name
                disease_part = disease_part.replace("This is", "").replace("The disease is", "").replace("This appears to be", "").strip()
                disease = disease_part.split("\n")[0].split(".")[0].strip()
                # Limit to first 4 words max
                words = disease.split()
                if len(words) > 4:
                    disease = " ".join(words[:4])
            
            if "DESCRIPTION:" in text_output:
                desc_part = text_output.split("DESCRIPTION:")[1].split("TREATMENT:")[0].strip() if "TREATMENT:" in text_output else text_output.split("DESCRIPTION:")[1].strip()
                description = desc_part.strip()
            
            if "TREATMENT:" in text_output:
                treatment_part = text_output.split("TREATMENT:")[1].strip()
                treatment = treatment_part.strip()

    return {
        "disease": disease or "Could not detect disease",
        "description": description or "No description available",
        "treatment": treatment or "No treatment suggestion available"
    }
