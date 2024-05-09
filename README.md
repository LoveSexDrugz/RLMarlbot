# RLMarlbot

Bot player based on my [python SDK](https://github.com/MarlBurroW/RLSDK-Python) and RLBot standard.
I recommend to look at the RLSDK-Python repository to understand how the bot works.

## Disclaimer

⚠️⚠️⚠️ RLMarlbot is designed to facilitate the use of bots in private matches with your friends without the need for RLBot. It should be used primarily for testing and debugging by botmakers. However, this tool employs advanced reverse engineering techniques that could legitimately be considered cheating by the game's standards. I strongly advise against using RLMarlbot in ranked or casual matches. Your Rocket League account is likely to be banned quickly if you violate this rule.

## Requirements
- [Poetry](https://python-poetry.org/) to install dependencies
- RocketLeague Epic (x64) running
- Python 3.11.0 (x64)
- Pyinstaller if you want to build the exe


## CLI Options

```
usage: main.py [-h] [-p PID] [-b BOT] [--kickoff] [--minimap] [--monitoring] [--debug-keys] [--clock] [--debug]

RLMarlbot

options:
  -h, --help         show this help message and exit
  -p PID, --pid PID  Rocket League process ID
  -b BOT, --bot BOT  Bot to use (nexto, necto, seer, element)
  --kickoff          Override all bots kickoff with a default one that is pretty good. 1 to enable, 0 to disable
  --minimap          Enable minimap
  --monitoring       Enable monitoring
  --debug-keys       Print all keys pressed in game in the console (Gamepad and Keyboard)
  --clock            Sync ticks with an internal clock at 120Hz, can help in case of unstable FPS ingame
  --debug            Show debug information in the console
```


## Installation

```bash	
# Clone the repository
git clone https://github.com/MarlBurroW/RLMarlbot

# Change directory
cd RLMarlbot

# Install dependencies
poetry install

# Enter poetry shell
poetry shell

# Run the game before running the script 
python .\rlmarlbot\main.py
```

## Build binary from source

```bash
pyinstaller .\main.spec
```

## Updates
If the repo is not up to date, you must git pull and update dependencies:
```bash
# get latest changes
git pull
# Update dependencies
poetry install
```


## Memory Writer
Source of the memory writer are in the folder `MemoryWriter`.
The compiled binary is here:  `rlnexto_python/memory_writer/memory_writer.pyd` so you don't need to compile the memory writer yourself because the binary is versioned.

## How does it works ?

RLMarlbot is a bot that uses the RLSDK Python package to read data from RocketLeague.exe. It uses the data to build a GameTickPacket (Structure of data defined by RLBot framework) and put the data into the Nexto RLBot agent. The Agent compute data in the AI torch model and return a SimpleControllerState that contains the car inputs data. Then inputs are written in the game memory with a native python library written in C++ (memory_writer.pyd) to be able to overwrite car inputs faster than the game loop.

## Discord
I created a discord so the community can discuss improvements, bugs, or just help each other.
[[https://discord.gg/pfsBQAqZ](https://discord.gg/EcsCWGEt67)](https://discord.gg/EcsCWGEt67)

## Credits

- **Rolv-Arild** - Necto/Nexto model + RLBot agent
- **Thorami**: For giving me some very useful tips, especially on how to obtain the base addresses of GNames and GObjects.
- **RLBot**: For having created a standard interface for bot creation.
- **Bardak**: For testing
- **Kxqs**: For help the community and his feedbacks
- **AScriver**: Contribute to improve the RLSDK
