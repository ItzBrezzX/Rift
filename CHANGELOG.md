# Changelog

## 0.2.0

- Multi-signal detection (structure, metadata, PE prefixes, dependencies) with weighted confidence.  
- Strategies: native export, migration, compatibility layer, generic preparation, already-Android.  
- Static PE parser (machine, imports, CLR) — never executes images.  
- ZIP symlink, encryption, and compression-ratio limits.  
- Job state machine; Android package jobs fail with `missing_toolchain` / `execution_disabled`.  
- Stopped reporting `native_apk_buildable_from_upload_alone: true`.  
- Engine adapters that describe official commands and refuse to pretend they ran.  
- Full documentation set.

## 0.1.0

- ZIP upload, basic filename fingerprints, single-page report.
