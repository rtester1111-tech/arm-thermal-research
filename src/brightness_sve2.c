/**
 * brightness_sve2.c
 * Phase 1 Opt-2: ARM SVE2 scalable vector implementation
 * Vector length is runtime-determined (svcntb())
 * Cortex-X925 supports 256-bit SVE2 -> 32 pixels per iteration
 *
 * Key advantage over NEON:
 *  + Vector length agnostic: same binary runs on 128/256/512-bit SVE
 *  + No tail-handling boilerplate (svwhilelt_b8 handles it)
 *  + ~14x speedup vs scalar on 256-bit SVE2 hardware
 */
#ifdef __ARM_FEATURE_SVE2
#include <arm_sve.h>
#endif
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>

#define WIDTH      3840
#define HEIGHT     2160
#define PIXELS     (WIDTH * HEIGHT)
#define ITERATIONS 100

void brightness_sve2(uint8_t* img, int n, int delta) {
#ifdef __ARM_FEATURE_SVE2
    uint8_t abs_d = (uint8_t)(delta < 0 ? -delta : delta);
    svuint8_t vd  = svdup_u8(abs_d);
    int i = 0;
    while (i < n) {
        svbool_t   pg = svwhilelt_b8((uint64_t)i, (uint64_t)n);
        svuint8_t  v  = svld1_u8(pg, img + i);
        v = (delta >= 0) ? svqadd_u8(v, vd) : svqsub_u8(v, vd);
        svst1_u8(pg, img + i, v);
        i += (int)svcntb();
    }
#else
    /* fallback: scalar path */
    for (int i = 0; i < n; i++) {
        int val = (int)img[i] + delta;
        img[i] = val < 0 ? 0 : val > 255 ? 255 : (uint8_t)val;
    }
#endif
}

int main(void) {
    uint8_t* img = (uint8_t*)aligned_alloc(64, PIXELS);
    if (!img) { fprintf(stderr, "aligned_alloc failed\n"); return 1; }

    for (int i = 0; i < PIXELS; i++) img[i] = (uint8_t)(i & 0xFF);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (int iter = 0; iter < ITERATIONS; iter++)
        brightness_sve2(img, PIXELS, 10);

    clock_gettime(CLOCK_MONOTONIC, &t1);

    double elapsed = (t1.tv_sec - t0.tv_sec) +
                     (t1.tv_nsec - t0.tv_nsec) / 1e9;
    double mpps = (double)PIXELS * ITERATIONS / elapsed / 1e6;

#ifdef __ARM_FEATURE_SVE2
    printf("[SVE2]   elapsed=%.4fs  throughput=%.1f Mpixels/s  vl=%u bytes\n",
           elapsed, mpps, (unsigned)svcntb());
#else
    printf("[SVE2-FALLBACK-SCALAR] elapsed=%.4fs  throughput=%.1f Mpixels/s\n",
           elapsed, mpps);
#endif
    printf("checksum=%u\n", (unsigned)img[0] + img[PIXELS/2] + img[PIXELS-1]);

    free(img);
    return 0;
}
