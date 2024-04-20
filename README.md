RLMarlbot

Nexto bot based on my python SDK: https://github.com/MarlBurroW/RLSDK-Python
I recommend to look at the RLSDK-Python repository to understand how the bot works.

Requirements
Poetry: https://python-poetry.org/ to install dependencies
RocketLeague Epic (x64) running
Installation
# Clone the repository
git clone https://github.com/MarlBurroW/RLMarlbot

# Change directory
cd RLMarlbot

# Install dependencies
poetry install

# Enter poetry shell
poetry shell

# Run the game before running the script 
python .\rlnexto_python\main.py
How does it works ?
RLMarlbot is a bot that uses the RLSDK Python package to read data from RocketLeague.exe. It uses the data to build a GameTickPacket (Structure of data defined by RLBot framework) and put the data into the Nexto RLBot agent. The Agent compute data in the AI torch model and return a SimpleControllerState that contains the car inputs data. Then inputs are written in the game memory with a native python library written in C++ (memory_writer.pyd) to be able to overwrite car inputs faster than the game loop.
