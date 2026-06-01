/*
 * stress_lcg.c — Minimal AArch64 compute-stress workload for gem5 task-trace
 *
 * Replaces the python3 inline LCG that hung in Timing mode.  Compiled C has
 * no interpreter startup cost so the workload actually runs.
 *
 * Usage:  stress_lcg [iterations]   (default: 500000)
 *
 * Output lines:
 *   [STRESS] START  pid=<N> iters=<N> cpu=<N>
 *   [STRESS] DONE   x=0x<hex> cpu=<N>
 *
 * CPU field: processor column from /proc/self/stat (field 39, 0-indexed).
 * The shell's [SAMPLER] loop reads the same field externally via /proc/<pid>/stat.
 *
 * Cross-compile:
 *   aarch64-linux-gnu-gcc -O2 -o stress_lcg stress_lcg.c
 *   # or with musl for a static binary:
 *   aarch64-linux-musl-gcc -static -O2 -o stress_lcg stress_lcg.c
 *
 * Place the binary at a path reachable in the gem5 rootfs, e.g. /root/stress_lcg
 * or copy into the disk image with a chosen mount point, for example:
 *   mount -o loop <disk.img> <mount-point>
 *   cp stress_lcg <mount-point>/root/
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>

/*
 * get_cpu() — read processor field (39) from /proc/self/stat.
 *
 * /proc/self/stat format (man 5 proc):
 *   pid (comm) state ppid pgrp session tty_nr tpgid flags
 *   minflt cminflt majflt cmajflt utime stime cutime cstime
 *   priority nice num_threads itrealvalue starttime vsize rss rsslim
 *   startcode endcode startstack kstkesp kstkeip signal blocked
 *   sigignore sigcatch wchan nswap cnswap exit_signal processor  <- field 39
 *
 * We skip past ')' (end of comm, which may contain spaces) then count
 * 36 whitespace-delimited tokens to reach field 39 = processor.
 */
static int get_cpu(void)
{
    FILE *f = fopen("/proc/self/stat", "r");
    if (!f) return -1;

    char buf[1024];
    if (!fgets(buf, sizeof(buf), f)) { fclose(f); return -1; }
    fclose(f);

    /* Skip past the closing ')' of the comm field. */
    char *p = buf;
    while (*p && *p != ')') p++;
    if (!*p) return -1;
    p++;  /* skip ')' */

    /* Skip 36 space-separated tokens (state through exit_signal). */
    int skipped = 0;
    while (*p && skipped < 36) {
        while (*p == ' ' || *p == '\t') p++;  /* skip leading whitespace */
        while (*p && *p != ' ' && *p != '\t' && *p != '\n') p++;  /* skip token */
        skipped++;
    }
    while (*p == ' ' || *p == '\t') p++;  /* skip whitespace before processor */

    return (*p) ? atoi(p) : -1;
}

int main(int argc, char *argv[])
{
    int iters = 500000;
    if (argc > 1) {
        iters = atoi(argv[1]);
        if (iters <= 0) iters = 500000;
    }

    int cpu_start = get_cpu();
    printf("[STRESS] START  pid=%d iters=%d cpu=%d\n",
           (int)getpid(), iters, cpu_start);
    fflush(stdout);

    /* Linear Congruential Generator — same constants as the Python rcS version. */
    uint64_t x = UINT64_C(0xDEADBEEFCAFEBABE);
    for (int i = 0; i < iters; i++) {
        x = x * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    }

    int cpu_end = get_cpu();
    printf("[STRESS] DONE   x=0x%016llx cpu=%d\n",
           (unsigned long long)x, cpu_end);
    fflush(stdout);

    return 0;
}
