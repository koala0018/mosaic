# Third-party Notices

This project can bundle third-party runtime packages when building distributable Windows packages.

## Lada

- Project: https://github.com/ladaapp/lada
- License: AGPL-3.0
- Use in this project: external executable runtime (`lada-cli.exe`)

The `mosaic` source repository does not vendor Lada source code. Build scripts may download an official Lada release package into `vendor/lada`, which is ignored by Git and bundled into local Windows distribution artifacts.

If you distribute a package that includes Lada binaries, keep Lada's license files and provide the Lada source/project link with the distributed package.

