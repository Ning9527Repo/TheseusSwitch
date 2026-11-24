# Link interface provenance

`libroothide.tbd` is a checked-in **link-time interface only**, not an implementation and never packaged. Runtime implementation comes from `Depends: roothide (>= 0.0.1)`.

Authoritative upstream: https://github.com/roothide/libroothide/tree/cb236f9cf1c5e2ac932611328998a62b4b133e33

- `Makefile` target `libroothide.dylib`: `-install_name @loader_path/.jbroot/usr/lib/libroothide.dylib`.
- `roothide.h`: C exports rootfs_alloc, jbroot_alloc, jbrootat_alloc, jbrand, jbroot, rootfs.
- `control`: package roothide, version 0.0.1, architecture iphoneos-arm64e.
- `roothide.h` is preserved in packaging/include/roothide/ with its MIT license. C exports only are represented in the minimal TBD. Use its const char * interface or an actual devkit when overloads are needed.
- Build uses `-needed-lroothide` so the final Mach-O has a genuine LC_LOAD_DYLIB even if physical resource path resolution makes a direct call unnecessary. Strict verification requires that install name in the RootHide main Mach-O, and forbids it in rootless packages. No local fake dylib is produced or shipped.

