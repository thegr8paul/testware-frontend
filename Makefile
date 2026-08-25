default: pytest

pytest:
	@pytest

# ----------------------------------
#         LOCAL SET UP
# ----------------------------------

install_requirements:
	@pip install -r requirements.txt

# ----------------------------------
#         RUN APP LOCALLY
# ----------------------------------

streamlit:
	-@streamlit run app.py

# ----------------------------------
#    CLEAN UP
# ----------------------------------

clean:
	@rm -fr */__pycache__
	@rm -fr .pytest_cache
	@rm -fr build
	@rm -fr dist
	@rm -fr *.egg-info
