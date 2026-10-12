/*
 * Read cumulative CPU time and pthread names for this process's Mach threads.
 * This diagnostic helper is used only by profile_fastapi_loop_cpu.py.
 */

#include <mach/mach.h>
#include <mach/thread_info.h>
#include <pthread.h>
#include <stdint.h>
#include <string.h>

typedef struct {
  uint64_t thread_id;
  uint64_t user_time_ns;
  uint64_t system_time_ns;
  char name[64];
} UvicornRsThreadCpuSample;

static uint64_t time_value_to_ns(time_value_t value) {
  return (uint64_t)value.seconds * 1000000000ULL +
         (uint64_t)value.microseconds * 1000ULL;
}

int uvicorn_rs_thread_cpu_snapshot(UvicornRsThreadCpuSample *output,
                                   int capacity) {
  if (output == NULL || capacity <= 0) {
    return -1;
  }

  thread_act_array_t threads = NULL;
  mach_msg_type_number_t thread_count = 0;
  if (task_threads(mach_task_self(), &threads, &thread_count) != KERN_SUCCESS) {
    return -2;
  }

  int written = 0;
  for (mach_msg_type_number_t index = 0;
       index < thread_count && written < capacity; index++) {
    thread_basic_info_data_t basic = {0};
    mach_msg_type_number_t basic_count = THREAD_BASIC_INFO_COUNT;
    if (thread_info(threads[index], THREAD_BASIC_INFO, (thread_info_t)&basic,
                    &basic_count) != KERN_SUCCESS) {
      continue;
    }

    thread_identifier_info_data_t identifier = {0};
    mach_msg_type_number_t identifier_count = THREAD_IDENTIFIER_INFO_COUNT;
    if (thread_info(threads[index], THREAD_IDENTIFIER_INFO,
                    (thread_info_t)&identifier,
                    &identifier_count) != KERN_SUCCESS) {
      continue;
    }

    UvicornRsThreadCpuSample *sample = &output[written++];
    sample->thread_id = identifier.thread_id;
    sample->user_time_ns = time_value_to_ns(basic.user_time);
    sample->system_time_ns = time_value_to_ns(basic.system_time);
    memset(sample->name, 0, sizeof(sample->name));

    pthread_t pthread = pthread_from_mach_thread_np(threads[index]);
    if (pthread != NULL) {
      (void)pthread_getname_np(pthread, sample->name, sizeof(sample->name));
    }
  }

  for (mach_msg_type_number_t index = 0; index < thread_count; index++) {
    (void)mach_port_deallocate(mach_task_self(), threads[index]);
  }
  (void)vm_deallocate(mach_task_self(), (vm_address_t)threads,
                      thread_count * sizeof(thread_t));
  return written;
}
