#!/bin/bash
# LeRobot Operator Console Setup Script
# For Ubuntu/Debian/Jetson

set -e

echo "========================================="
echo "LeRobot Operator Console Setup"
echo "========================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $PYTHON_VERSION"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies..."
pip install -r requirements.txt

# udev rules
if [ -d "udev" ] && [ -f "udev/99-so100.rules" ]; then
    echo ""
    echo "Installing udev rules for serial port access..."
    sudo cp udev/99-so100.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo "✓ udev rules installed"
fi

# Add user to dialout group
echo ""
echo "Adding user to dialout group for serial access..."
sudo usermod -aG dialout $USER
echo "✓ User added to dialout group"

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "IMPORTANT: Log out and back in for group changes to take effect."
echo ""
echo "To run the application:"
echo "  1. source .venv/bin/activate"
echo "  2. python app.py"
echo ""
echo "Or simply run:"
echo "  .venv/bin/python app.py"
echo ""


