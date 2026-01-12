# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the requirements file into the container
COPY requirements.txt .

# Install base requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install the naoqi_proxy_client package from the golden image source
COPY --from=pepper-box:01-26-latest /home/pepperdev/py3-naoqi-bridge /usr/src/PepperBox/py3-naoqi-bridge
RUN pip install /usr/src/PepperBox/py3-naoqi-bridge

# Copy the rest of the application's code into the container
# Define the command to run your app
CMD ["python", "-m", "pepper_wizard.main"]
