#ifdef __ARM_NEON
#include <arm_neon.h>
#endif
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>

#define WIDTH      640
#define HEIGHT     480
#define PIXELS     (WIDTH * HEIGHT)
#define ITERATIONS 50  // 640*480*50 = 15.36M Pixels, enough to trigger temperature rise but fast in gem5

void brightness_neon(uint8_t* img, int n, int delta) {
#ifdef __ARM_NEON
    uint8_t  abs_delta = (uint8_t)(delta < 0 ? -delta : delta);
    uint8x16_t vd = vdupq_n_u8(abs_delta);
    int i = 0;
    for (; i <= n - 16; i += 16) {
        uint8x16_t v = vld1q_u8(img + i);
        v = (delta >= 0) ? vqaddq_u8(v, vd) : vqsubq_u8(v, vd);
        vst1q_u8(img + i, v);
    }
    for (; i < n; i++) {
        int val = (int)img[i] + delta;
        img[i] = val < 0 ? 0 : val > 255 ? 255 : (uint8_t)val;
    }
#else
    for (int i = 0; i < n; i++) {
        int val = (int)img[i] + delta;
        img[i] = val < 0 ? 0 : val > 255 ? 255 : (uint8_t)val;
    }
#endif
}

int main(void) {
    uint8_t* img = (uint8_t*)aligned_alloc(16, PIXELS);
    if (!img) { fprintf(stderr, "aligned_alloc failed\n"); return 1; }

    for (int i = 0; i < PIXELS; i++) img[i] = (uint8_t)(i & 0xFF);

    printf("[GEM5-WORKLOAD] Starting NEON brightness workload (%dx%d, %d iterations)...\n", WIDTH, HEIGHT, ITERATIONS);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (int iter = 0; iter < ITERATIONS; iter++) {
        brightness_neon(img, PIXELS, 15);
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);

    double elapsed = (t1.tv_sec - t0.tv_sec) +
                     (t1.tv_nsec - t0.tv_nsec) / 1e9;
    double mpps = (double)PIXELS * ITERATIONS / elapsed / 1e6;

#ifdef __ARM_NEON
    printf("[NEON]   elapsed=%.4fs  throughput=%.1f Mpixels/s\n", elapsed, mpps);
#else
    printf("[NEON-FALLBACK-SCALAR] elapsed=%.4fs  throughput=%.1f Mpixels/s\n", elapsed, mpps);
#endif
    printf("checksum=%u\n", (unsigned)img[0] + img[PIXELS/2] + img[PIXELS-1]);

    free(img);
    return 0;
}
