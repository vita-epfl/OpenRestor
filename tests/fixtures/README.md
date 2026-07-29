# Phase 1 Test Fixture

The test suite generates short, deterministic 44.1 kHz stereo PCM WAV files at runtime. Keeping
the fixture synthetic avoids committing licensed music while exercising ingestion, source-level
splitting, canonical 30-second rendering, checksum verification, sharding, and statistics.
