# Stage 1: Get the library
FROM ghcr.io/action-prediction-lab/pepper-box:v2.3.1@sha256:cb296a2ac483ac7d5789bc0367227464b191c6da9110b9db5c565bb81938d8f8 AS bridge-source

# Stage 2: Build the Wizard
FROM python:3.9-slim@sha256:2d97f6910b16bd338d3060f261f53f144965f755599aab1acda1e13cf1731b1b

# Set the working directory in the container
WORKDIR /usr/src/app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Every pip install takes package versions from constraints.txt, the package list of the v2.3.1 image
COPY constraints.txt .
ENV PIP_CONSTRAINT=/usr/src/app/constraints.txt

# Install base requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install the naoqi_proxy_client package from the image
COPY --from=bridge-source /home/pepperdev/py3-naoqi-bridge /usr/src/PepperBox/py3-naoqi-bridge
RUN pip install /usr/src/PepperBox/py3-naoqi-bridge



# Pre-download the NLP model validation during build
COPY pepper_wizard/utils/download_model.py .
RUN python download_model.py

# Copy the rest of the application's code into the container
COPY pepper_wizard ./pepper_wizard

# Define the command to run your app
CMD ["python", "-m", "pepper_wizard.main"]
