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

# Local mock of the RAG backend (mock_api.py) so the UI works offline.
# Run in a separate terminal from `make streamlit`.
mock:
	@MOCK_DELAY=$${MOCK_DELAY:-2} python mock_api.py

# Same mock with a 20s delay, to see the "thinking" animation / loading states.
mock_slow:
	@MOCK_DELAY=20 python mock_api.py

# ----------------------------------
#    CLEAN UP
# ----------------------------------

clean:
	@rm -fr */__pycache__
	@rm -fr .pytest_cache
	@rm -fr build
	@rm -fr dist
	@rm -fr *.egg-info
