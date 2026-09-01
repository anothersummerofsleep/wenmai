# Reference provenance (public)

Provenance for the official English translation used as a **post-hoc published comparison reference**
in the LOTM reference analysis. The reference is not a gold-standard answer key; the Chinese source
remains the primary evidence, and matching the official translation is not correctness.

- **Reference:** official English translation of the Chinese source
- **Chapters:** 1-10
- **Alignment:** clean 1:1 chapter alignment (each file one chapter; English titles match the Chinese
  source chapter titles; opening scenes correspond; natural chapter endings)
- **Access timing:** the official English translation was accessed **only after** the blind benchmark
  was generated, evaluated, unblinded, curated, and its cumulative checkpoint published; after the
  reference-analysis protocol was frozen; and after the 77-item comparison universe was preregistered.
  It was not available to generation, evaluation, curation, or the blind aggregate analysis.
- **First reference-content inspection:** 2026-09-01 (recorded at protocol Phase 2, chapter-alignment
  check). Before that step only filenames and byte checksums were taken.

The raw reference text is **not** published (copyright); it is stored locally and git-ignored. The
exact acquisition source is recorded only in the private, git-ignored provenance manifest.

## Freeze commits (all precede reference exposure)

| Stage | Commit |
|---|---|
| Blind 10-chapter checkpoint | `070d4f0b12ae82f93143b217c6d9c27414881e36` |
| Reference-analysis protocol freeze | `bb678c3f196d44ceeee9e98274400a6c9afc392b` |
| Preregistered comparison universe | `c6eb1abdfe58cf13a1eee46b2cb8dcbf37d3cb7e` |

Preregistered inventory SHA-256: `4f5f2abbfbdb54fd9754a0a646acf4a01d04b488ea32c1e491f499e25c0e6b32`

## Reference files (byte-level provenance)

| Chapter | File | Title | Bytes | SHA-256 |
|---|---|---|---|---|
| 1 | ch00001_en.txt | Crimson (绯红) | 8697 | cb6d45846b85627919349ca74fa6a1238afff765491ec7afba28071f262c418b |
| 2 | ch00002_en.txt | Situation (情况) | 13040 | e6e700b30e35222ba86193edd8c882e557a3cba2727c865009a7d959170e7f54 |
| 3 | ch00003_en.txt | Melissa (梅丽莎) | 12637 | 0f74f0aa7fc04fd09fa2f319e478648dde331ea19db8d31d2c72c65fef0185a5 |
| 4 | ch00004_en.txt | Divination (占卜) | 15059 | 4f24f9f8e266429362d868a9a8c54c51226c8b42d7e58e54a44398cba75e768d |
| 5 | ch00005_en.txt | Ritual (仪式) | 14205 | 3ec3d7d2114a70c7842f232c017a1d5350955cf017fa11e682b1a1888238dce1 |
| 6 | ch00006_en.txt | Beyonder (非凡者) | 12786 | 29ac2ff2bfc53783fe179af6f8537a12946410439d9ea05fb85c861e1a5ebccb |
| 7 | ch00007_en.txt | Code Names (代号) | 12457 | 939dd63473221ecdcb9e18ee4b26688d643c34b37c99da591310451575e26708 |
| 8 | ch00008_en.txt | A New Era (新的时代) | 15458 | 3d9af3143e0c67f2427003af600a02ef3b6b3d5ddceadbfd1f1add0be7245002 |
| 9 | ch00009_en.txt | The Notebook (笔记) | 13498 | db7727ac5e6d37c479ef53afb208cb0dc4d5cb4dc59a3a75e42f3a63f9fa17e7 |
| 10 | ch00010_en.txt | The Norm (常态) | 11129 | 910ea312f9e1bcbcdb0796bf5ff485e8684557905f00c1060335a307519c22e5 |

Checksums let a holder of the same official English chapters verify byte-identical provenance without
the text being redistributed here.
