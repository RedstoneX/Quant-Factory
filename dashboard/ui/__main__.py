"""Run the read-only Quant Factory Dashboard."""

from dashboard.ui.app import app


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
