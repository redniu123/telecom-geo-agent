from __future__ import annotations

import hashlib
import json

import pytest

from scripts.generate_demo_data import write_demo_data
from telecom_core.data_loader import DataValidationError, load_demo_network, load_network, load_sites

from conftest import write_json


def test_fixed_demo_loads_with_unique_ids_and_site_bindings():
    network = load_demo_network()

    assert set(network.sites) == {"A", "B"}
    assert network.sites["A"]["site_type"] == "telecom_room"
    assert network.sites["B"]["site_type"] == "base_station"
    assert network.sites["A"]["node_id"] == "N1"
    assert network.sites["B"]["node_id"] == "N4"
    assert len(network.nodes) == len(set(network.nodes)) == 5
    assert len(network.edge_records) == len(set(network.edge_records)) == 6


def test_coordinates_are_wgs84_longitude_latitude_and_lines_have_two_points():
    network = load_demo_network()

    for node in network.nodes.values():
        longitude, latitude = node["geometry"]["coordinates"]
        assert -180 <= longitude <= 180
        assert -90 <= latitude <= 90
    for edge in network.edge_records.values():
        coordinates = edge["geometry"]["coordinates"]
        assert edge["geometry"]["type"] == "LineString"
        assert len(coordinates) >= 2
        assert coordinates[0] == network.nodes[edge["from_node"]]["geometry"]["coordinates"]
        assert coordinates[-1] == network.nodes[edge["to_node"]]["geometry"]["coordinates"]


def test_generator_is_byte_for_byte_repeatable(tmp_path):
    first_paths = write_demo_data(tmp_path)
    first_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in first_paths]

    second_paths = write_demo_data(tmp_path)
    second_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in second_paths]

    assert first_hashes == second_hashes
    for path in second_paths:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["metadata"]["seed"] == 20260904
        assert "not a real engineering dataset" in parsed["metadata"]["source"]


def test_missing_required_edge_field_fails_with_file_feature_and_field(tmp_path, demo_documents):
    _, network_document = demo_documents
    edge = next(feature for feature in network_document["features"] if feature["id"] == "edge:D017")
    del edge["properties"]["length_m"]
    path = write_json(tmp_path / "missing.geojson", network_document)

    with pytest.raises(DataValidationError) as error:
        load_network(path)

    message = str(error.value)
    assert str(path) in message
    assert "edge:D017" in message
    assert "length_m" in message


def test_bad_node_reference_fails_closed(tmp_path, demo_documents):
    _, network_document = demo_documents
    edge = next(feature for feature in network_document["features"] if feature["id"] == "edge:D017")
    edge["properties"]["to_node"] = "MISSING"
    path = write_json(tmp_path / "bad-node.geojson", network_document)

    with pytest.raises(DataValidationError, match="edge:D017.*to_node.*MISSING"):
        load_network(path)


def test_negative_length_fails_closed(tmp_path, demo_documents):
    _, network_document = demo_documents
    edge = next(feature for feature in network_document["features"] if feature["id"] == "edge:D017")
    edge["properties"]["length_m"] = -1
    path = write_json(tmp_path / "negative.geojson", network_document)

    with pytest.raises(DataValidationError, match="edge:D017.*length_m.*greater than zero"):
        load_network(path)


def test_invalid_coordinate_reports_exact_feature_and_coordinate_field(tmp_path, demo_documents):
    sites_document, _ = demo_documents
    sites_document["features"][0]["geometry"]["coordinates"] = [31.23, 181]
    path = write_json(tmp_path / "bad-coordinate.geojson", sites_document)

    with pytest.raises(DataValidationError, match=r"site:A.*geometry\.coordinates.*latitude"):
        load_sites(path)


def test_duplicate_edge_id_fails_closed(tmp_path, demo_documents):
    _, network_document = demo_documents
    duplicate = next(feature for feature in network_document["features"] if feature["id"] == "edge:D017")
    clone = json.loads(json.dumps(duplicate))
    clone["id"] = "edge:D017-copy"
    network_document["features"].append(clone)
    path = write_json(tmp_path / "duplicate.geojson", network_document)

    with pytest.raises(DataValidationError, match="duplicate edge ID 'D017'"):
        load_network(path)


def test_used_cores_cannot_exceed_capacity(tmp_path, demo_documents):
    _, network_document = demo_documents
    edge = next(feature for feature in network_document["features"] if feature["id"] == "edge:D001")
    edge["properties"]["used_cores"] = edge["properties"]["capacity_cores"] + 1
    path = write_json(tmp_path / "capacity.geojson", network_document)

    with pytest.raises(DataValidationError, match="edge:D001.*used_cores.*capacity_cores"):
        load_network(path)


def test_site_binding_must_reference_existing_node(tmp_path, demo_documents):
    sites_document, network_document = demo_documents
    sites_document["features"][0]["properties"]["node_id"] = "MISSING"
    sites_path = write_json(tmp_path / "sites.geojson", sites_document)
    network_path = write_json(tmp_path / "network.geojson", network_document)

    with pytest.raises(DataValidationError, match="site:A.*node_id.*MISSING"):
        load_demo_network(network_path, sites_path)
