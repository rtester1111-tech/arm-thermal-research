/**
 * idct_sve2.c
 * Phase 1 Opt-2: ARM SVE2 scalable vector implementation of 8x8 2D IDCT
 * Scalable vector logic using svcnth() and svwhilelt_b16() predicate lanes
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
#define BLOCK_SIZE 8
#define PIXELS     (WIDTH * HEIGHT)
#define NUM_BLOCKS (PIXELS / (BLOCK_SIZE * BLOCK_SIZE))
#define ITERATIONS 10

static const int16_t C[8][8] = {
    {64,  64,  64,  64,  64,  64,  64,  64},
    {89,  75,  50,  18, -18, -50, -75, -89},
    {83,  36, -36, -83, -83, -36,  36,  83},
    {75, -18, -89, -50,  50,  89,  18, -75},
    {64, -64, -64,  64,  64, -64, -64,  64},
    {50, -89,  18,  75, -75, -18,  89, -50},
    {36, -83,  83, -36, -36,  83, -83,  36},
    {18, -50,  75, -89,  89, -75,  50, -18}
};

void idct_8x8_block_sve2(const int16_t* in, uint8_t* out, int stride) {
#ifdef __ARM_FEATURE_SVE2
    int16_t tmp[8][8];
    svbool_t pg8 = svwhilelt_b16(0, 8); // Active predicate for exactly 8 elements

    // 1. Transform rows
    for (int i = 0; i < 8; i++) {
        svint16_t vin = svld1_s16(pg8, in + i * 8);
        for (int j = 0; j < 8; j++) {
            svint16_t vc_j = svld1_s16(pg8, C[j]);
            svint16_t vprod = svmul_s16_z(pg8, vin, vc_j);
            int32_t sum = svaddv_s16(pg8, vprod);
            tmp[i][j] = (int16_t)(sum >> 6);
        }
    }

    // 2. Transform columns and clamp
    for (int i = 0; i < 8; i++) {
        svint16_t vrow_c = svld1_s16(pg8, C[i]);
        for (int j = 0; j < 8; j++) {
            int16_t col[8];
            for (int k = 0; k < 8; k++) col[k] = tmp[k][j];
            svint16_t vcol = svld1_s16(pg8, col);

            svint16_t vprod = svmul_s16_z(pg8, vrow_c, vcol);
            int32_t sum = svaddv_s16(pg8, vprod);
            int val = sum >> 12;
            out[i * stride + j] = val < 0 ? 0 : val > 255 ? 255 : (uint8_t)val;
        }
    }
#else
    // Fallback scalar path
    int16_t tmp[8][8];
    for (int i = 0; i < 8; i++) {
        for (int j = 0; j < 8; j++) {
            int sum = 0;
            for (int k = 0; k < 8; k++) {
                sum += in[i * 8 + k] * C[j][k];
            }
            tmp[i][j] = (int16_t)(sum >> 6);
        }
    }
    for (int j = 0; j < 8; j++) {
        for (int i = 0; i < 8; i++) {
            int sum = 0;
            for (int k = 0; k < 8; k++) {
                sum += C[i][k] * tmp[k][j];
            }
            int val = sum >> 12;
            out[i * stride + j] = val < 0 ? 0 : val > 255 ? 255 : (uint8_t)val;
        }
    }
#endif
}

void idct_frame_sve2(const int16_t* coeff, uint8_t* img) {
    for (int by = 0; by < HEIGHT / 8; by++) {
        for (int bx = 0; bx < WIDTH / 8; bx++) {
            int block_idx = by * (WIDTH / 8) + bx;
            const int16_t* block_in = coeff + block_idx * 64;
            uint8_t* block_out = img + by * 8 * WIDTH + bx * 8;
            idct_8x8_block_sve2(block_in, block_out, WIDTH);
        }
    }
}

int main(void) {
    int16_t* coeff = (int16_t*)aligned_alloc(64, PIXELS * sizeof(int16_t));
    uint8_t* img = (uint8_t*)aligned_alloc(64, PIXELS);
    if (!coeff || !img) { fprintf(stderr, "aligned_alloc failed\n"); return 1; }

    for (int i = 0; i < PIXELS; i++) {
        coeff[i] = (int16_t)(((i % 64) == 0) ? (128 + (i % 256)) : ((i % 7) - 3));
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (int iter = 0; iter < ITERATIONS; iter++) {
        idct_frame_sve2(coeff, img);
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);

    double elapsed = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
    double mpps = (double)PIXELS * ITERATIONS / elapsed / 1e6;

#ifdef __ARM_FEATURE_SVE2
    printf("[IDCT-SVE2]   elapsed=%.4fs  throughput=%.1f Mpixels/s  vl=%u bytes\n", elapsed, mpps, (unsigned)svcntb());
#else
    printf("[IDCT-SVE2-FALLBACK-SCALAR] elapsed=%.4fs  throughput=%.1f Mpixels/s\n", elapsed, mpps);
#endif
    printf("checksum=%u\n", (unsigned)img[0] + img[PIXELS/2] + img[PIXELS-1]);

    free(coeff);
    free(img);
    return 0;
}
