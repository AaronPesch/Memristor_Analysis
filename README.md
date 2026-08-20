# memristor-analysis
A Python GUI for the analysis and visualization of Memristor(RRAM) I–V characteristics as part of TU Darmstadt's Team Project Software Engineering (TPSE).

To set up the needed dependencies run the following commands:
1. pip install virtualenv (if not already installed)
2. virtualenv venv
3. source venv/bin/activate
4. pip install -r requirements.txt

For developers:
After adding a new package to the venv, the current state can be saved with the following command.
pip freeze > requirements.txt