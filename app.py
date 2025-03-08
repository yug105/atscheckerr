import os
import json
import PyPDF2 as pdf
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure Google Generative AI
genai.configure(api_key=os.getenv("GOOGLE_API"))

# Initialize Flask app
app = Flask(__name__)
# Enable CORS to allow requests from your Next.js frontend
CORS(app)

def get_available_models():
    """List available models to debug"""
    try:
        models = genai.list_models()
        model_names = [model.name for model in models]
        return model_names
    except Exception as e:
        return f"Error listing models: {str(e)}"

def get_gemini_response(text, jd):
    """Get response from Gemini model"""
    try:
        model_name='models/gemini-1.5-flash'
        
        # Create the model
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
        Hey Act Like a skilled or very experience ATS(Application Tracking System)
        with a deep understanding of tech field, software engineering, data science, data analyst
        and big data engineer. Your task is to evaluate the resume based on the given job description.
        You must consider the job market is very competitive and you should provide 
        best assistance for improving the resumes. Assign the percentage Matching based 
        on JD and the missing keywords with high accuracy
        
        resume:{text}
        description:{jd}
        
        I want the response in one single string having the structure
        {{"JD Match":"%","MissingKeywords":[],"Profile Summary":""}}
        """
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        app.logger.error(f"Error from Gemini API: {str(e)}")
        # Try fallback to a simplified response
        fallback_response = {
            "JD Match": "0%",
            "MissingKeywords": ["API error occurred"],
            "Profile Summary": f"Unable to analyze resume: {str(e)}. Please try again later."
        }
        return json.dumps(fallback_response)

def input_pdf_text(uploaded_file):
    """Extract text from uploaded PDF file"""
    try:
        reader = pdf.PdfReader(uploaded_file)
        text = ""
        for page in range(len(reader.pages)):
            page = reader.pages[page]
            text += str(page.extract_text())
        return text
    except Exception as e:
        app.logger.error(f"Error extracting text from PDF: {str(e)}")
        raise Exception(f"Could not extract text from PDF: {str(e)}")

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint that also lists available models"""
    models = get_available_models()
    return jsonify({
        "status": "healthy", 
        "message": "ATS API is running",
        "available_models": models
    }), 200

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Endpoint to analyze resume against job description"""
    if 'resume' not in request.files:
        return jsonify({"error": "No resume file provided"}), 400
        
    resume_file = request.files['resume']
    job_description = request.form.get('job_description', '')
    
    if resume_file.filename == '':
        return jsonify({"error": "No resume file selected"}), 400
        
    if not job_description:
        return jsonify({"error": "No job description provided"}), 400
    
    # Check if file is a PDF
    if not resume_file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "File must be a PDF"}), 400
    
    try:
        # Extract text from PDF
        resume_text = input_pdf_text(resume_file)
        
        # Check if text was successfully extracted
        if not resume_text or len(resume_text.strip()) < 10:
            return jsonify({"error": "Could not extract sufficient text from PDF. Please check if the PDF contains selectable text."}), 400
        
        # Get analysis from Gemini
        gemini_response = get_gemini_response(resume_text, job_description)
        
        # Try to parse the JSON response
        try:
            # Sometimes the AI might return a raw JSON string with escaped quotes
            # First, try to parse directly
            result = json.loads(gemini_response)
        except json.JSONDecodeError:
            # If direct parsing fails, try to clean the string
            # This handles cases where the AI might return markdown code blocks or other formatting
            clean_response = gemini_response.strip()
            
            # Remove markdown code blocks if present
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]  # Remove ```json
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]  # Remove ```
                
            clean_response = clean_response.strip()
            
            try:
                result = json.loads(clean_response)
            except json.JSONDecodeError:
                # If still can't parse, return a fallback response
                result = {
                    "JD Match": "N/A",
                    "MissingKeywords": ["Could not parse response"],
                    "Profile Summary": "The system encountered an error analyzing your resume. Please try again."
                }
        
        # Return the result
        return jsonify(result), 200
        
    except Exception as e:
        app.logger.error(f"Error in analyze endpoint: {str(e)}")
        return jsonify({
            "error": str(e),
            "JD Match": "0%",
            "MissingKeywords": ["Error occurred"],
            "Profile Summary": f"Error analyzing resume: {str(e)}"
        }), 500

if __name__ == '__main__':
    # Get port from environment variable or use 5000 as default
    port = int(os.environ.get("PORT", 8000))
    # Use 0.0.0.0 to make the server publicly available if deployed
    app.run(host='0.0.0.0', port=port, debug=True)