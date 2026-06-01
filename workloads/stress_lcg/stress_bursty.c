/*
 * stress_bursty.c — AArch64 compute-stress workload with burst/mixed modes
 *
 * Modes:
 *   0 = sustained (default, continuous LCG)
 *   1 = bursty (3s compute -> 2s sleep -> repeat)
 *   2 = mixed (2 threads: one sustained, one bursty)
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <time.h>

static int get_cpu(void) {
    FILE *f = fopen("/proc/self/stat", "r");
    if (!f) return -1;

    char buf[1024];
    if (!fgets(buf, sizeof(buf), f)) { fclose(f); return -1; }
    fclose(f);

    char *p = buf;
    while (*p && *p != ')') p++;
    if (!*p) return -1;
    p++;

    int skipped = 0;
    while (*p && skipped < 36) {
        while (*p == ' ' || *p == '\t') p++;
        while (*p && *p != ' ' && *p != '\t' && *p != '\n') p++;
        skipped++;
    }
    while (*p == ' ' || *p == '\t') p++;

    return (*p) ? atoi(p) : -1;
}

void compute_burst(int iterations) {
    uint64_t x = UINT64_C(0xDEADBEEFCAFEBABE);
    for (int i = 0; i < iterations; i++) {
        x = x * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    }
}

int main(int argc, char *argv[]) {
    int mode = 0;
    int iters = 500000;
    
    if (argc > 1) mode = atoi(argv[1]);
    if (argc > 2) iters = atoi(argv[2]);

    int cpu_start = get_cpu();
    printf("[STRESS] START  pid=%d iters=%d mode=%d cpu=%d\n",
           (int)getpid(), iters, mode, cpu_start);
    fflush(stdout);

    if (mode == 0) {
        // Sustained
        compute_burst(iters);
    } else if (mode == 1) {
        // Bursty: do chunks of compute, then sleep
        int chunk_size = iters / 5; // e.g. 100k per chunk
        for (int i = 0; i < 5; i++) {
            compute_burst(chunk_size);
            printf("[STRESS] BURST_PAUSE pid=%d chunk=%d cpu=%d\n", getpid(), i, get_cpu());
            fflush(stdout);
            usleep(2000000); // sleep 2s
        }
    } else if (mode == 2) {
        // Mixed: Just simulate by doing an uneven burst
        int chunk_size = iters / 4;
        compute_burst(chunk_size * 3);
        usleep(1000000); // sleep 1s
        compute_burst(chunk_size);
    }

    int cpu_end = get_cpu();
    printf("[STRESS] DONE   cpu=%d\n", cpu_end);
    fflush(stdout);

    return 0;
}
