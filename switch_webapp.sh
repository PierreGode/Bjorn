#!/bin/bash
# Switch between old and new Bjorn web interfaces

BJORN_PY="/home/bjorn/Bjorn/Bjorn.py"

echo "================================"
echo "Bjorn Web Interface Switcher"
echo "================================"
echo ""
echo "Current status:"
if grep -q "from webapp_modern import" "$BJORN_PY" 2>/dev/null; then
    echo "✓ Using MODERN interface (Flask + Tailwind)"
    CURRENT="modern"
else
    echo "✓ Using OLD interface (SimpleHTTPRequestHandler)"
    CURRENT="old"
fi
echo ""
echo "What would you like to do?"
echo "1. Switch to MODERN interface (recommended)"
echo "2. Switch to OLD interface"
echo "3. Exit"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        if [ "$CURRENT" == "modern" ]; then
            echo "Already using modern interface!"
        else
            echo "Switching to modern interface..."
            # Backup current file
            cp "$BJORN_PY" "${BJORN_PY}.backup"
            # Switch to modern webapp
            sed -i 's/from webapp import web_thread/from webapp_modern import run_server as web_thread/' "$BJORN_PY"
            echo "✓ Switched to modern interface"
            echo "Restarting Bjorn service..."
            sudo systemctl restart bjorn
            echo "✓ Done! Access at http://$(hostname -I | awk '{print $1}'):8000"
        fi
        ;;
    2)
        if [ "$CURRENT" == "old" ]; then
            echo "Already using old interface!"
        else
            echo "Switching to old interface..."
            # Backup current file
            cp "$BJORN_PY" "${BJORN_PY}.backup"
            # Switch to old webapp
            sed -i 's/from webapp_modern import run_server as web_thread/from webapp import web_thread/' "$BJORN_PY"
            echo "✓ Switched to old interface"
            echo "Restarting Bjorn service..."
            sudo systemctl restart bjorn
            echo "✓ Done! Access at http://$(hostname -I | awk '{print $1}'):8000"
        fi
        ;;
    3)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice!"
        exit 1
        ;;
esac
