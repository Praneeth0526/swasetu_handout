# -*- coding: utf-8 -*-
"""
Sewa Setu Evaluation Dashboard Routes.
Mounts public /evals dashboard and JSON APIs for the automated assessor and public audit.
"""

import os
import json
from flask import Blueprint, render_template, jsonify, request

from evals.eval_runner import run_benchmark, RESULTS_FILE

evals_bp = Blueprint("evals", __name__, url_prefix="/evals")


def _get_results():
    if not os.path.exists(RESULTS_FILE):
        return run_benchmark()
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return run_benchmark()


@evals_bp.route("", methods=["GET"])
@evals_bp.route("/", methods=["GET"])
def evals_dashboard():
    """Render public evaluation dashboard without requiring login."""
    data = _get_results()
    return render_template(
        "evals.html",
        metrics=data.get("metrics", {}),
        scenarios=data.get("scenarios", []),
        timestamp=data.get("timestamp", "")
    )


@evals_bp.route("/api/results", methods=["GET"])
def evals_api_results():
    """Return raw benchmark metrics in JSON format for automated evaluators."""
    data = _get_results()
    return jsonify(data), 200


@evals_bp.route("/api/run", methods=["POST"])
def evals_api_run():
    """Trigger real-time execution of evaluation benchmark suite."""
    try:
        results = run_benchmark()
        return jsonify({"success": True, "results": results}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
