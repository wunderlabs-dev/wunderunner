"""Integration tests for docker build activity."""

from unittest.mock import MagicMock, patch

import pytest
from docker.errors import ImageNotFound

from wunderunner.activities import docker
from wunderunner.exceptions import BuildError


class TestBuildActivity:
    """Integration tests for docker.build()."""

    @pytest.mark.asyncio
    async def test_fresh_build_creates_image(self, tmp_path):
        """Fresh build writes Dockerfile and builds image."""
        dockerfile_content = "FROM alpine:latest\nCMD echo hello"

        mock_image = MagicMock()
        mock_image.id = "sha256:abc123"

        mock_client = MagicMock()
        mock_client.images.get.side_effect = [
            ImageNotFound("not found"),  # First call: cache miss
            mock_image,  # Second call: after build
        ]
        mock_client.api.build.return_value = iter([
            {"stream": "Step 1/2 : FROM alpine:latest\n"},
            {"stream": "Step 2/2 : CMD echo hello\n"},
        ])

        with patch("wunderunner.activities.docker.get_client", return_value=mock_client):
            result = await docker.build(tmp_path, dockerfile_content)

            # Dockerfile should be written
            assert (tmp_path / "Dockerfile").exists()
            assert (tmp_path / "Dockerfile").read_text() == dockerfile_content

            # Result should indicate no cache hit
            assert result.cache_hit is False
            assert result.image_id == "sha256:abc123"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_build(self, tmp_path):
        """Cache hit returns existing image without building."""
        dockerfile_content = "FROM alpine:latest\nCMD echo hello"

        mock_image = MagicMock()
        mock_image.id = "sha256:cached123"

        mock_client = MagicMock()
        mock_client.images.get.return_value = mock_image  # Cache hit

        with patch("wunderunner.activities.docker.get_client", return_value=mock_client):
            result = await docker.build(tmp_path, dockerfile_content)

            # Should NOT call build API
            mock_client.api.build.assert_not_called()

            # Result should indicate cache hit
            assert result.cache_hit is True
            assert result.image_id == "sha256:cached123"

    @pytest.mark.asyncio
    async def test_different_content_different_tag(self, tmp_path):
        """Different Dockerfile content produces different cache tags."""
        content1 = "FROM alpine:latest\nCMD echo hello"
        content2 = "FROM alpine:latest\nCMD echo world"

        tag1 = docker._compute_cache_tag(tmp_path, content1)
        tag2 = docker._compute_cache_tag(tmp_path, content2)

        assert tag1 != tag2
        assert tag1.startswith("wunderunner-")
        assert tag2.startswith("wunderunner-")

    @pytest.mark.asyncio
    async def test_different_path_different_tag(self, tmp_path):
        """Different project paths produce different cache tags."""
        content = "FROM alpine:latest\nCMD echo hello"

        path1 = tmp_path / "project1"
        path2 = tmp_path / "project2"
        path1.mkdir()
        path2.mkdir()

        tag1 = docker._compute_cache_tag(path1, content)
        tag2 = docker._compute_cache_tag(path2, content)

        assert tag1 != tag2

    @pytest.mark.asyncio
    async def test_build_error_raises_build_error(self, tmp_path):
        """Build failure raises BuildError with logs."""
        dockerfile_content = "FROM nonexistent:image"

        mock_client = MagicMock()
        mock_client.images.get.side_effect = ImageNotFound("not found")
        mock_client.api.build.return_value = iter([
            {"stream": "Step 1/1 : FROM nonexistent:image\n"},
            {"error": "pull access denied for nonexistent"},
        ])

        with (
            patch("wunderunner.activities.docker.get_client", return_value=mock_client),
            pytest.raises(BuildError, match="Docker build failed"),
        ):
            await docker.build(tmp_path, dockerfile_content)

    @pytest.mark.asyncio
    async def test_build_completes_but_image_missing_raises(self, tmp_path):
        """Build completes without error but image not found raises BuildError."""
        dockerfile_content = "FROM alpine:latest"

        mock_client = MagicMock()
        mock_client.images.get.side_effect = ImageNotFound("not found")  # Always not found
        mock_client.api.build.return_value = iter([
            {"stream": "Step 1/1 : FROM alpine:latest\n"},
        ])

        with (
            patch("wunderunner.activities.docker.get_client", return_value=mock_client),
            pytest.raises(BuildError, match="image not created"),
        ):
            await docker.build(tmp_path, dockerfile_content)


class TestCacheTagGeneration:
    """Unit tests for cache tag generation."""

    def test_tag_format(self, tmp_path):
        """Tag follows expected format."""
        content = "FROM alpine"
        tag = docker._compute_cache_tag(tmp_path, content)

        assert tag.startswith("wunderunner-")
        parts = tag.split("-")
        assert len(parts) == 3
        # Each hash part should be 8 characters
        assert len(parts[1]) == 8
        assert len(parts[2]) == 8

    def test_tag_is_deterministic(self, tmp_path):
        """Same inputs produce same tag."""
        content = "FROM alpine"

        tag1 = docker._compute_cache_tag(tmp_path, content)
        tag2 = docker._compute_cache_tag(tmp_path, content)

        assert tag1 == tag2


class TestImageExists:
    """Unit tests for image existence check."""

    def test_image_exists_returns_true(self):
        """Returns True when image exists."""
        mock_client = MagicMock()
        mock_client.images.get.return_value = MagicMock()

        assert docker._image_exists(mock_client, "test:tag") is True

    def test_image_not_found_returns_false(self):
        """Returns False when image not found."""
        mock_client = MagicMock()
        mock_client.images.get.side_effect = ImageNotFound("not found")

        assert docker._image_exists(mock_client, "test:tag") is False
