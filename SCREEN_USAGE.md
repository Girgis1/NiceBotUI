# Multi-Screen Support

## Usage

To start the app on a specific screen (monitor):

```bash
# Start on primary screen (default)
python3 app.py

# Start on secondary screen (fullscreen)
python3 app.py --screen 1

# Start on secondary screen (windowed mode)
python3 app.py --screen 1 --windowed

# Start on third screen
python3 app.py --screen 2
```

## Screen Numbering

- `--screen 0` = Primary monitor (default)
- `--screen 1` = Secondary monitor  
- `--screen 2` = Third monitor
- etc.

## Options

- `--screen N` - Screen number to display on
- `--windowed` - Run in windowed mode (1024x600) instead of fullscreen
- `--no-fullscreen` - Same as `--windowed`

## Examples

### Production Setup (Secondary Screen, Fullscreen)
```bash
python3 app.py --screen 1
```

### Development Setup (Primary Screen, Windowed)
```bash
python3 app.py --windowed
```

### Testing on Specific Screen
```bash
python3 app.py --screen 2 --windowed
```


