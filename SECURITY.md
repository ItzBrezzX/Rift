# Security

Uploaded archives are untrusted.

## Enforced

- ZIP names normalized to forward slashes  
- Absolute paths, drive prefixes, `..`, and NUL bytes rejected (`zip_slip`)  
- Unix symlink entries rejected  
- Encrypted entries rejected  
- Entry count, uncompressed size, and compression-ratio ceilings (`zip_bomb`)  
- PE parsing is in-process and does not execute the image  
- Build commands are fixed adapter strings — not read from ZIP shell metadata  
- Job execution of editors is off in v0.2  

## Not enforced here

- Malware scanning  
- Authentication (do not expose publicly as shipped)  
- Disk quotas beyond `PORT_ENGINE_MAX_UPLOAD_BYTES`  

## Operations

Run as non-root in a container without release keystores mounted. Delete `data/uploads` on a schedule. Do not commit proprietary game files.
