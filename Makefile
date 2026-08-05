PYTHON := ./venv/bin/python
NODE   := node
PLAYER_HTML := /tmp/player.html

.PHONY: test test-py test-js clean

test: test-py test-js

test-py:
	$(PYTHON) -m pytest tests/ -q

test-js: $(PLAYER_HTML)
	$(NODE) tests/player_js.test.js $(PLAYER_HTML)

$(PLAYER_HTML): tests/dump_player_html.py
	PYTHONPATH=. $(PYTHON) tests/dump_player_html.py $(PLAYER_HTML)

clean:
	rm -f $(PLAYER_HTML)
