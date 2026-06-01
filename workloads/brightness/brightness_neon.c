/**
 * brightness_neon.c
 * Phase 1 Opt-1: ARM NEON 128-bit SIMD implementation
 * Processes 16 pixels per iteration using vqaddq_u8/vqsubq_u8
 *
 * Trade-offs vs scalar:
 *  + ~8-10x throughput improvement
 *  + Saturating add (no manual clamp needed)
 *  - Higher instantaneous power draw (~1.8x scalar)
 *  - Requires 16-byte aligned buffer for best performance
 *  - Tail handling needed if n % 16 != 0
 */
#ifdef __ARM_NEON
#include <arm_neon.h>
#endif
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>

#define WIDTH      3840
#define HEIGHT     2160
#define PIXELS     (WIDTH * HEIGHT)
#define ITERATIONS 100

void brightness_neon(uint8_t* img, int n, int delta) {
#ifdef __ARM_NEON
    uint8_t  abs_delta = (uint8_t)(delta < 0 ? -delta : delta);
    uint8x16_t vd = vdupq_n_u8(abs_delta);
    int i = 0;
    /* vectorised body: 16 pixels per iteration */
    for (; i <= n - 16; i += 16) {
        uint8x16_t v = vld1q_u8(img + i);
        v = (delta >= 0) ? vqaddq_u8(v, vd) : vqsubq_u8(v, vd);
        vst1q_u8(img + i, v);
    }
    /* scalar tail */
    for (; i < n; i++) {
        int val = (int)img[i] + delta;
        img[i] = val < 0 ? 0 : val > 255 ? 255 : (uint8_t)val;
    }
#else
    /* fallback scalar path on non-NEON platforms */
    for (int i = 0; i < n; i++) {
        int val = (int)img[i] + delta;
        img[i] = val < 0 ? 0 : val > 255 ? 255 : (uint8_t)val;
    }
#endif
}

int main(void) {
    /* 16-byte aligned allocation for optimal NEON performance */
    uint8_t* img = (uint8_t*)aligned_alloc(16, PIXELS);
    if (!img) { fprintf(stderr, "aligned_alloc failed\n"); return 1; }

    for (int i = 0; i < PIXELS; i++) img[i] = (uint8_t)(i & 0xFF);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (int iter = 0; iter < ITERATIONS; iter++)
        brightness_neon(img, PIXELS, 10);

    clock_gettime(CLOCK_MONOTONIC, &t1);

    double elapsed = (t1.tv_sec - t0.tv_sec) +
                     (t1.tv_nsec - t0.tv_nsec) / 1e9;
    double mpps = (double)PIXELS * ITERATIONS / elapsed / 1e6;

#ifdef __ARM_NEON
    printf("[NEON]   elapsed=%.4fs  throughput=%.1f Mpixels/s\n", elapsed, mpps);
#else
    printf("[NEON-FALLBACK-SCALAR] elapsed=%.4fs  throughput=%.1f Mpixels/s\n",
           elapsed, mpps);
#endif
    printf("checksum=%u\n", (unsigned)img[0] + img[PIXELS/2] + img[PIXELS-1]);

    free(img);
    return 0;
}
