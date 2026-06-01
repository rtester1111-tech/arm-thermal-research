/**
 * brightness_scalar.c
 * Phase 1 Baseline: Pure scalar C implementation
 * 4K brightness adjustment kernel (no SIMD)
 */
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>

#define WIDTH  3840
#define HEIGHT 2160
#define PIXELS (WIDTH * HEIGHT)
#define ITERATIONS 100

static inline uint8_t clamp_u8(int v) {
    if (v < 0)   return 0;
    if (v > 255) return 255;
    return (uint8_t)v;
}

void brightness_scalar(uint8_t* img, int n, int delta) {
    for (int i = 0; i < n; i++) {
        img[i] = clamp_u8((int)img[i] + delta);
    }
}

int main(void) {
    uint8_t* img = (uint8_t*)malloc(PIXELS);
    if (!img) { fprintf(stderr, "malloc failed\n"); return 1; }

    /* init with test pattern */
    for (int i = 0; i < PIXELS; i++) img[i] = (uint8_t)(i & 0xFF);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (int iter = 0; iter < ITERATIONS; iter++)
        brightness_scalar(img, PIXELS, 10);

    clock_gettime(CLOCK_MONOTONIC, &t1);

    double elapsed = (t1.tv_sec - t0.tv_sec) +
                     (t1.tv_nsec - t0.tv_nsec) / 1e9;
    double mpps = (double)PIXELS * ITERATIONS / elapsed / 1e6;

    printf("[SCALAR] elapsed=%.4fs  throughput=%.1f Mpixels/s\n",
           elapsed, mpps);
    printf("checksum=%u\n", (unsigned)img[0] + img[PIXELS/2] + img[PIXELS-1]);

    free(img);
    return 0;
}
