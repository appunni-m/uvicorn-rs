# Normal release after HTTP/3 request-task reaping

Source, Cargo manifests/lockfile, build identity, completed release build log,
formatting log and completed Clippy log are byte-identical copies from the
original build directory. The identity records the exact source and installed
native SHA, compiler, build arguments, link flags and zero instrumentation
marker counts. No native binary is committed. The empty formatting log is
preserved without fabricating output; existing build/check logs were read,
not rerun by the archival command.

This binary produced the `../h3-task-reaping/after/` memory diagnostic. Those
five response/shutdown observations passed, while every timing row was invalid
due to host contention. This build identity alone is not a full public ASGI
parity gate or speed proof. Its owner will append the completed public
exact-binary gate separately; archive manifests then require refreshing.
