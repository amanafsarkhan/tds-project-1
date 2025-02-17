# Use an official Ubuntu base image
FROM ubuntu:latest

# Set the maintainer label
#LABEL maintainer="your_email@example.com"

# Update the repository sources list and install necessary packages
RUN apt-get update && apt-get install -y \
    build-essential \
    python3 \
    python3-pip \
    npm \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install npx and prettier globally
RUN npm install -g npx prettier


# Download the latest uv installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"

# Set the working directory
WORKDIR /

# Copy the application source code to the container
COPY app.py /

# Expose the port the application runs on
EXPOSE 8000

# Command to run the application
CMD ["uv", "run", "app.py"]
