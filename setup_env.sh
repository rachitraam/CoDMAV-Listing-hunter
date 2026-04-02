
#!/bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "Environment setup complete. Please restart your IDE or select the 'venv' interpreter."
