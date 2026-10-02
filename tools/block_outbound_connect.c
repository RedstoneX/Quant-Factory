/* Test-only LD_PRELOAD guard: permit local IPC, reject non-loopback connect(). */
#define _GNU_SOURCE

#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <netinet/in.h>
#include <stddef.h>
#include <sys/socket.h>

typedef int (*connect_function)(int, const struct sockaddr *, socklen_t);

static int address_is_allowed(const struct sockaddr *address, socklen_t length) {
    if (address == NULL) {
        return 1;
    }
    if (address->sa_family == AF_UNIX) {
        return 1;
    }
    if (address->sa_family == AF_INET && length >= sizeof(struct sockaddr_in)) {
        const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)address;
        return (ntohl(ipv4->sin_addr.s_addr) >> 24) == 127;
    }
    if (address->sa_family == AF_INET6 && length >= sizeof(struct sockaddr_in6)) {
        const struct sockaddr_in6 *ipv6 = (const struct sockaddr_in6 *)address;
        return IN6_IS_ADDR_LOOPBACK(&ipv6->sin6_addr);
    }
    return 0;
}

int connect(int socket_fd, const struct sockaddr *address, socklen_t length) {
    static connect_function real_connect = NULL;

    if (!address_is_allowed(address, length)) {
        errno = EPERM;
        return -1;
    }
    if (real_connect == NULL) {
        real_connect = (connect_function)dlsym(RTLD_NEXT, "connect");
        if (real_connect == NULL) {
            errno = ENOSYS;
            return -1;
        }
    }
    return real_connect(socket_fd, address, length);
}
