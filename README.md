# VideoAgent Setup Instructions

To set this project up on a completely new computer, here are the steps you will need to follow:

### 1. Prerequisites (System Installs)
First, you'll need to install the core software on the new computer:
* **Python**: Download and install Python (make sure to check the box "Add Python to PATH" during installation).
* **DaVinci Resolve**: Install DaVinci Resolve (Note: Ensure "External Scripting" is enabled in Resolve's preferences under System -> General, set to Local).
* **Git**: Install Git to clone the repository.
* **FFmpeg** *(Required for Whisper)*: Whisper requires FFmpeg to process audio. You'll need to install FFmpeg and add it to your system's PATH.

### 2. Download the Project
Open a terminal (or Command Prompt/PowerShell) and clone your new GitHub repository:
```bash
git clone https://github.com/akhimnt/VideoAgent.git
cd VideoAgent
```

### 3. Set Up the Python Environment
It's best practice to create a virtual environment so the packages don't conflict with other projects.
```bash
# Create a virtual environment named 'venv'
python -m venv venv

# Activate it (on Windows)
venv\Scripts\activate

# Install all the packages we saved
pip install -r requirements.txt
```

### 4. Configure Your Keys
Since we purposefully ignored your `.env` file (to keep your API keys safe), you will need to recreate it on the new machine.
1. Copy the `.env.template` file and rename the copy to `.env`.
2. Open the `.env` file and paste in your `GEMINI_API_KEY`.
3. *(Optional)* Update the `RESOLVE_INSTALL_PATH` if DaVinci Resolve is installed in a different location on the new machine.

### 5. Run the App
Once everything above is done, make sure DaVinci Resolve is open, and then run your app:
```bash
python app.py
```
