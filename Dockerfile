# Stage 1: Get the library
FROM jwgcurrie/pepper-box:01-26-latest AS bridge-source

# Stage 2: Build the Wizard
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install base requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install the naoqi_proxy_client package from the image
COPY --from=bridge-source /home/pepperdev/py3-naoqi-bridge /usr/src/PepperBox/py3-naoqi-bridge
RUN pip install /usr/src/PepperBox/py3-naoqi-bridge



# Pre-download the NLP model validation during build
COPY pepper_wizard/utils/download_model.py .
RUN python download_model.py

# Copy the rest of the application's code into the container
# Define the command to run your app
CMD ["python", "-m", "pepper_wizard.main"]
