"""
Unit tests for the audio feature extraction service (app.services.audio_features).

Tests cover:
- LOCAL_DEV mode mock audio features
- extract_audio_features() with mocked librosa
- Pitch extraction (PYIN) with normal and edge cases
- Energy extraction (RMS)
- Spectral centroid (clarity)
- Silence ratio calculation
- extract_audio_features_from_s3() S3 download flow
- Edge cases: silence, very short audio, all-voiced/unvoiced
"""
import numpy as np
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# LOCAL_DEV mode tests
# ---------------------------------------------------------------------------

class TestLocalDevMode:
    """Tests for LOCAL_DEV mock audio features."""

    def test_returns_mock_features_structure(self):
        """In LOCAL_DEV, should return a dict with all expected keys."""
        from app.services.audio_features import extract_audio_features
        result = extract_audio_features("/fake/path.wav")

        assert "duration_sec" in result
        assert "sample_rate" in result
        assert "pitch" in result
        assert "energy" in result
        assert "clarity" in result
        assert "silence_ratio" in result
        assert "summary" in result

    def test_mock_pitch_has_required_fields(self):
        """Mock pitch should have mean, std, min, max, range, voiced_ratio."""
        from app.services.audio_features import extract_audio_features
        result = extract_audio_features("/fake/path.wav")
        pitch = result["pitch"]

        assert "mean_hz" in pitch
        assert "std_hz" in pitch
        assert "min_hz" in pitch
        assert "max_hz" in pitch
        assert "range_hz" in pitch
        assert "voiced_ratio" in pitch

    def test_mock_energy_has_required_fields(self):
        """Mock energy should have mean, std, max, dynamic_range_db."""
        from app.services.audio_features import extract_audio_features
        result = extract_audio_features("/fake/path.wav")
        energy = result["energy"]

        assert "mean" in energy
        assert "std" in energy
        assert "max" in energy
        assert "dynamic_range_db" in energy

    def test_mock_summary_has_derived_flags(self):
        """Mock summary should have is_monotone, has_good_energy_variation, silence_percentage."""
        from app.services.audio_features import extract_audio_features
        result = extract_audio_features("/fake/path.wav")
        summary = result["summary"]

        assert "is_monotone" in summary
        assert "has_good_energy_variation" in summary
        assert "silence_percentage" in summary
        assert isinstance(summary["is_monotone"], bool)
        assert isinstance(summary["has_good_energy_variation"], bool)

    def test_mock_values_are_realistic(self):
        """Mock values should be in realistic ranges."""
        from app.services.audio_features import extract_audio_features
        result = extract_audio_features("/fake/path.wav")

        # Human pitch range roughly 80-400 Hz
        assert 80 < result["pitch"]["mean_hz"] < 400
        assert result["pitch"]["std_hz"] > 0
        assert 0 < result["pitch"]["voiced_ratio"] <= 1.0

        # Silence should be a fraction
        assert 0 <= result["silence_ratio"] <= 1.0

        # Duration should be positive
        assert result["duration_sec"] > 0


# ---------------------------------------------------------------------------
# Feature extraction with mocked librosa
# ---------------------------------------------------------------------------

class TestExtractAudioFeatures:
    """Tests for extract_audio_features() with mocked librosa."""

    @pytest.fixture
    def mock_librosa(self):
        """Create a mock librosa module with realistic returns."""
        mock = MagicMock()

        # librosa.load returns (audio array, sample_rate)
        # 2 seconds of audio at 22050 Hz
        duration = 2.0
        sr = 22050
        n_samples = int(duration * sr)
        y = np.random.randn(n_samples).astype(np.float32) * 0.1
        mock.load.return_value = (y, sr)
        mock.get_duration.return_value = duration

        # librosa.pyin returns (f0, voiced_flag, voiced_probs)
        n_frames = 100
        f0 = np.full(n_frames, 180.0)
        f0[::5] = np.nan  # some unvoiced frames
        voiced_flag = ~np.isnan(f0)
        voiced_probs = np.where(voiced_flag, 0.9, 0.1)
        mock.pyin.return_value = (f0, voiced_flag, voiced_probs)
        mock.note_to_hz.side_effect = lambda note: {"C2": 65.41, "C7": 2093.0}[note]

        # librosa.feature.rms
        rms = np.random.uniform(0.01, 0.1, size=(1, n_frames))
        mock.feature.rms.return_value = rms

        # librosa.feature.spectral_centroid
        sc = np.random.uniform(1000, 3000, size=(1, n_frames))
        mock.feature.spectral_centroid.return_value = sc

        return mock

    def test_returns_all_required_keys(self, mock_librosa, monkeypatch):
        """Should return dict with duration, pitch, energy, clarity, silence_ratio, summary."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            import importlib, app.config.settings
            importlib.reload(app.config.settings)
            import app.services.audio_features
            importlib.reload(app.services.audio_features)

            result = app.services.audio_features.extract_audio_features("/fake/path.wav")

        assert "duration_sec" in result
        assert "pitch" in result
        assert "energy" in result
        assert "clarity" in result
        assert "silence_ratio" in result
        assert "summary" in result

    def test_pitch_statistics_calculated(self, mock_librosa, monkeypatch):
        """Should calculate pitch mean, std, min, max, range from PYIN output."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            import importlib, app.config.settings
            importlib.reload(app.config.settings)
            import app.services.audio_features
            importlib.reload(app.services.audio_features)

            result = app.services.audio_features.extract_audio_features("/fake/path.wav")

        pitch = result["pitch"]
        assert pitch["mean_hz"] > 0
        assert pitch["range_hz"] >= 0
        assert 0 < pitch["voiced_ratio"] <= 1.0

    def test_monotone_detection(self, mock_librosa, monkeypatch):
        """Monotone should be True when pitch std < 15 Hz."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        # Set pitch to constant (std = 0)
        f0 = np.full(100, 180.0)
        voiced = np.ones(100, dtype=bool)
        mock_librosa.pyin.return_value = (f0, voiced, np.ones(100) * 0.9)

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            import importlib, app.config.settings
            importlib.reload(app.config.settings)
            import app.services.audio_features
            importlib.reload(app.services.audio_features)

            result = app.services.audio_features.extract_audio_features("/fake/path.wav")

        assert result["summary"]["is_monotone"] is True
        assert result["pitch"]["std_hz"] < 15

    def test_non_monotone_detection(self, mock_librosa, monkeypatch):
        """Non-monotone should be detected when pitch has good variation."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        # Set pitch with high variation
        f0 = np.linspace(120, 300, 100)
        voiced = np.ones(100, dtype=bool)
        mock_librosa.pyin.return_value = (f0, voiced, np.ones(100) * 0.9)

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            import importlib, app.config.settings
            importlib.reload(app.config.settings)
            import app.services.audio_features
            importlib.reload(app.services.audio_features)

            result = app.services.audio_features.extract_audio_features("/fake/path.wav")

        assert result["summary"]["is_monotone"] is False
        assert result["pitch"]["std_hz"] > 15

    def test_energy_dynamic_range(self, mock_librosa, monkeypatch):
        """Dynamic range should be calculated from RMS min/max ratio in dB."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            import importlib, app.config.settings
            importlib.reload(app.config.settings)
            import app.services.audio_features
            importlib.reload(app.services.audio_features)

            result = app.services.audio_features.extract_audio_features("/fake/path.wav")

        assert result["energy"]["dynamic_range_db"] > 0

    def test_silence_ratio_range(self, mock_librosa, monkeypatch):
        """Silence ratio should be between 0 and 1."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        with patch.dict("sys.modules", {"librosa": mock_librosa}):
            import importlib, app.config.settings
            importlib.reload(app.config.settings)
            import app.services.audio_features
            importlib.reload(app.services.audio_features)

            result = app.services.audio_features.extract_audio_features("/fake/path.wav")

        assert 0 <= result["silence_ratio"] <= 1.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge case inputs."""

    def test_all_unvoiced_pitch(self, monkeypatch):
        """When all frames are unvoiced, pitch stats should be zero."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        mock_lib = MagicMock()
        mock_lib.load.return_value = (np.zeros(22050), 22050)
        mock_lib.get_duration.return_value = 1.0
        mock_lib.pyin.return_value = (
            np.full(50, np.nan),  # all NaN = unvoiced
            np.zeros(50, dtype=bool),
            np.zeros(50),
        )
        mock_lib.note_to_hz.side_effect = lambda note: {"C2": 65.41, "C7": 2093.0}[note]
        mock_lib.feature.rms.return_value = np.ones((1, 50)) * 0.01
        mock_lib.feature.spectral_centroid.return_value = np.ones((1, 50)) * 1500

        with patch.dict("sys.modules", {"librosa": mock_lib}):
            import importlib, app.config.settings
            importlib.reload(app.config.settings)
            import app.services.audio_features
            importlib.reload(app.services.audio_features)

            result = app.services.audio_features.extract_audio_features("/fake/path.wav")

        assert result["pitch"]["mean_hz"] == 0
        assert result["pitch"]["std_hz"] == 0
        assert result["pitch"]["range_hz"] == 0

    def test_silent_audio(self, monkeypatch):
        """Audio with all-zero energy should have high silence ratio."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        mock_lib = MagicMock()
        mock_lib.load.return_value = (np.zeros(22050), 22050)
        mock_lib.get_duration.return_value = 1.0
        mock_lib.pyin.return_value = (
            np.full(50, np.nan),
            np.zeros(50, dtype=bool),
            np.zeros(50),
        )
        mock_lib.note_to_hz.side_effect = lambda note: {"C2": 65.41, "C7": 2093.0}[note]
        mock_lib.feature.rms.return_value = np.zeros((1, 50))
        mock_lib.feature.spectral_centroid.return_value = np.zeros((1, 50))

        with patch.dict("sys.modules", {"librosa": mock_lib}):
            import importlib, app.config.settings
            importlib.reload(app.config.settings)
            import app.services.audio_features
            importlib.reload(app.services.audio_features)

            result = app.services.audio_features.extract_audio_features("/fake/path.wav")

        assert result["silence_ratio"] == 1.0
        assert result["energy"]["mean"] == 0


# ---------------------------------------------------------------------------
# S3 download flow
# ---------------------------------------------------------------------------

class TestExtractFromS3:
    """Tests for extract_audio_features_from_s3()."""

    def test_local_dev_uses_local_path(self):
        """In LOCAL_DEV, should use local upload path instead of S3."""
        import importlib, app.config.settings, app.services.audio_features
        importlib.reload(app.config.settings)
        importlib.reload(app.services.audio_features)
        from app.services.audio_features import extract_audio_features_from_s3

        with patch("app.services.audio_features.get_local_upload_path", return_value="/fake/path.wav") as mock_path, \
             patch("app.services.audio_features.extract_audio_features") as mock_extract:
            mock_extract.return_value = {"mocked": True}
            result = extract_audio_features_from_s3("bucket", "uploads/u1/file.webm")

        mock_path.assert_called_once_with("uploads/u1/file.webm")
        mock_extract.assert_called_once_with("/fake/path.wav")
        assert result == {"mocked": True}

    def test_s3_download_called_in_aws_mode(self, monkeypatch):
        """In AWS mode, should download file from S3 and extract features."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        mock_s3 = MagicMock()
        mock_s3.download_file.return_value = None

        import importlib, app.config.settings, app.services.audio_features
        importlib.reload(app.config.settings)
        importlib.reload(app.services.audio_features)

        with patch("app.services.audio_features.boto3") as mock_boto3, \
             patch("app.services.audio_features.extract_audio_features") as mock_extract, \
             patch("os.path.exists", return_value=True), \
             patch("os.remove"):
            mock_boto3.client.return_value = mock_s3
            mock_extract.return_value = {"mocked": True}

            result = app.services.audio_features.extract_audio_features_from_s3(
                "my-bucket", "uploads/u1/file.webm"
            )

        mock_s3.download_file.assert_called_once()
        call_args = mock_s3.download_file.call_args[0]
        assert call_args[0] == "my-bucket"
        assert call_args[1] == "uploads/u1/file.webm"
