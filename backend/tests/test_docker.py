"""Tests for the expanded Docker Container, Image, Volume, Network, and Template Manager."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_docker_status_and_service(client: AsyncClient, admin_headers: dict[str, str]):
    # Status
    res = await client.get("/api/v1/docker/status", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "installed" in data
    assert "active" in data
    assert "version" in data
    assert "info" in data

    # Service control
    svc_res = await client.post("/api/v1/docker/service/restart", headers=admin_headers)
    assert svc_res.status_code == 200
    assert svc_res.json()["ok"] is True

    # Install
    inst_res = await client.post("/api/v1/docker/install", headers=admin_headers)
    assert inst_res.status_code == 200
    assert inst_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_docker_containers_crud_and_actions(client: AsyncClient, admin_headers: dict[str, str]):
    # List containers
    list_res = await client.get("/api/v1/docker/containers", headers=admin_headers)
    assert list_res.status_code == 200
    assert "containers" in list_res.json()
    containers = list_res.json()["containers"]
    assert len(containers) >= 1

    # Filter running
    run_res = await client.get("/api/v1/docker/containers?status=running", headers=admin_headers)
    assert run_res.status_code == 200

    # Deploy new container
    run_req = {
        "name": "test-nginx-container",
        "image": "nginx:alpine",
        "ports": ["8085:80"],
        "env": {"FOO": "bar"},
        "volumes": ["test_vol:/data"],
        "restart_policy": "unless-stopped",
    }
    deploy_res = await client.post("/api/v1/docker/containers/run", headers=admin_headers, json=run_req)
    assert deploy_res.status_code == 200
    assert deploy_res.json()["ok"] is True

    # Container actions
    cid = containers[0]["ID"]
    for action in ["start", "restart", "pause", "unpause", "kill", "stop", "rm"]:
        act_res = await client.post(f"/api/v1/docker/containers/{cid}/{action}", headers=admin_headers)
        assert act_res.status_code == 200
        assert act_res.json()["ok"] is True

    # Logs
    log_res = await client.get(f"/api/v1/docker/containers/{cid}/logs?tail=50", headers=admin_headers)
    assert log_res.status_code == 200
    assert "logs" in log_res.json()

    # Inspect
    insp_res = await client.get(f"/api/v1/docker/containers/{cid}/inspect", headers=admin_headers)
    assert insp_res.status_code == 200

    # Exec
    exec_res = await client.post(
        f"/api/v1/docker/containers/{cid}/exec",
        headers=admin_headers,
        json={"command": "uptime"},
    )
    assert exec_res.status_code == 200
    assert exec_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_docker_images(client: AsyncClient, admin_headers: dict[str, str]):
    # List
    res = await client.get("/api/v1/docker/images", headers=admin_headers)
    assert res.status_code == 200
    assert "images" in res.json()
    assert len(res.json()["images"]) >= 1

    # Pull
    pull_res = await client.post("/api/v1/docker/images/pull", headers=admin_headers, json={"image": "redis:7-alpine"})
    assert pull_res.status_code == 200
    assert pull_res.json()["ok"] is True

    # Remove
    del_res = await client.delete("/api/v1/docker/images/redis:7-alpine", headers=admin_headers)
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_docker_volumes_and_networks(client: AsyncClient, admin_headers: dict[str, str]):
    # Volumes list
    v_res = await client.get("/api/v1/docker/volumes", headers=admin_headers)
    assert v_res.status_code == 200
    assert "volumes" in v_res.json()

    # Create volume
    v_create = await client.post("/api/v1/docker/volumes", headers=admin_headers, json={"name": "test_volume", "driver": "local"})
    assert v_create.status_code == 200
    assert v_create.json()["ok"] is True

    # Delete volume
    v_del = await client.delete("/api/v1/docker/volumes/test_volume", headers=admin_headers)
    assert v_del.status_code == 200
    assert v_del.json()["ok"] is True

    # Networks list
    n_res = await client.get("/api/v1/docker/networks", headers=admin_headers)
    assert n_res.status_code == 200
    assert "networks" in n_res.json()

    # Create network
    n_create = await client.post("/api/v1/docker/networks", headers=admin_headers, json={"name": "test_net", "driver": "bridge"})
    assert n_create.status_code == 200
    assert n_create.json()["ok"] is True

    # Delete network
    n_del = await client.delete("/api/v1/docker/networks/test_net", headers=admin_headers)
    assert n_del.status_code == 200
    assert n_del.json()["ok"] is True


@pytest.mark.asyncio
async def test_docker_prune_templates_and_compose(client: AsyncClient, admin_headers: dict[str, str]):
    # Prune
    prune_res = await client.post("/api/v1/docker/prune", headers=admin_headers, json={"all": True, "volumes": True})
    assert prune_res.status_code == 200
    assert prune_res.json()["ok"] is True

    # Templates catalog
    tmpl_res = await client.get("/api/v1/docker/templates", headers=admin_headers)
    assert tmpl_res.status_code == 200
    templates = tmpl_res.json()
    assert len(templates) >= 5

    # Deploy template
    deploy_tmpl = await client.post(
        "/api/v1/docker/templates/deploy",
        headers=admin_headers,
        json={"template_id": "redis", "name": "my-custom-redis", "ports": ["6380:6379"]},
    )
    assert deploy_tmpl.status_code == 200
    assert deploy_tmpl.json()["ok"] is True

    # Compose deploy
    comp_yaml = """version: '3.8'
services:
  web:
    image: nginx:alpine
    ports:
      - "8089:80"
"""
    comp_res = await client.post(
        "/api/v1/docker/compose/deploy",
        headers=admin_headers,
        json={"project_name": "sample_stack", "compose_yaml": comp_yaml},
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["ok"] is True

    # Compose down
    down_res = await client.post(
        "/api/v1/docker/compose/down",
        headers=admin_headers,
        json={"project_name": "sample_stack", "compose_yaml": comp_yaml},
    )
    assert down_res.status_code == 200
    assert down_res.json()["ok"] is True
