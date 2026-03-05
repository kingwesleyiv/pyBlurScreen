import ctypes
import time

import mss
import pygame
from OpenGL.GL import *


VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aUV;

out vec2 vUV;

void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    vUV = vec2(aUV.x, 1.0 - aUV.y);
}
"""


COPY_FRAGMENT_SHADER = """
#version 330 core
in vec2 vUV;
out vec4 FragColor;

uniform sampler2D uTexture;

void main() {
    FragColor = texture(uTexture, vUV);
}
"""


BLUR_FRAGMENT_SHADER = """
#version 330 core
in vec2 vUV;
out vec4 FragColor;

uniform sampler2D uTexture;
uniform vec2 uDirection;

void main() {
    vec2 off1 = uDirection * 3 * 1.3846153846;
    vec2 off2 = uDirection * 3 * 3.2307692308;

    vec4 color = texture(uTexture, vUV) * 0.2370270270;
    color += texture(uTexture, vUV + off1) * 0.3162162162;
    color += texture(uTexture, vUV - off1) * 0.3162162162;
    color += texture(uTexture, vUV + off2) * 0.0702702703;
    color += texture(uTexture, vUV - off2) * 0.0702702703;

    FragColor = color;
}
"""


BLUR_PASSES = 20
TARGET_FPS = 30


def compile_shader(source, shader_type):
    shader = glCreateShader(shader_type)
    glShaderSource(shader, source)
    glCompileShader(shader)

    if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
        error = glGetShaderInfoLog(shader).decode("utf-8", errors="replace")
        raise RuntimeError(error)

    return shader


def create_program(vertex_source, fragment_source):
    vertex_shader = compile_shader(vertex_source, GL_VERTEX_SHADER)
    fragment_shader = compile_shader(fragment_source, GL_FRAGMENT_SHADER)

    program = glCreateProgram()
    glAttachShader(program, vertex_shader)
    glAttachShader(program, fragment_shader)
    glLinkProgram(program)

    if glGetProgramiv(program, GL_LINK_STATUS) != GL_TRUE:
        error = glGetProgramInfoLog(program).decode("utf-8", errors="replace")
        raise RuntimeError(error)

    glDeleteShader(vertex_shader)
    glDeleteShader(fragment_shader)
    return program


def create_texture(width, height, upload_format):
    texture = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, texture)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexImage2D(
        GL_TEXTURE_2D,
        0,
        GL_RGBA8,
        width,
        height,
        0,
        upload_format,
        GL_UNSIGNED_BYTE,
        None,
    )
    return texture


def create_framebuffer(texture):
    framebuffer = glGenFramebuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, framebuffer)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0)

    if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
        raise RuntimeError("Failed to create framebuffer")

    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    return framebuffer


def create_fullscreen_quad():
    vertices = (ctypes.c_float * 16)(
        -1.0,
        -1.0,
        0.0,
        0.0,
        1.0,
        -1.0,
        1.0,
        0.0,
        1.0,
        1.0,
        1.0,
        1.0,
        -1.0,
        1.0,
        0.0,
        1.0,
    )
    indices = (ctypes.c_uint * 6)(0, 1, 2, 2, 3, 0)

    vao = glGenVertexArrays(1)
    vbo = glGenBuffers(1)
    ebo = glGenBuffers(1)

    glBindVertexArray(vao)

    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, ctypes.sizeof(vertices), vertices, GL_STATIC_DRAW)

    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, ctypes.sizeof(indices), indices, GL_STATIC_DRAW)

    stride = 4 * ctypes.sizeof(ctypes.c_float)
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
    glEnableVertexAttribArray(1)
    glVertexAttribPointer(
        1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(2 * ctypes.sizeof(ctypes.c_float))
    )

    glBindVertexArray(0)
    return vao, vbo, ebo


def draw_fullscreen(vao):
    glBindVertexArray(vao)
    glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_INT, None)
    glBindVertexArray(0)


def select_main_monitor(monitors):
    for monitor in monitors[1:]:
        if monitor.get("left", 1) == 0 and monitor.get("top", 1) == 0:
            return monitor
    return monitors[1]


def main():
    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(
        pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
    )

    with mss.mss() as capture:
        if len(capture.monitors) < 1:
            raise RuntimeError("No monitors detected")

        monitor = select_main_monitor(capture.monitors)
        source_width = int(monitor["width"])
        source_height = int(monitor["height"])

        window_width = max(1, source_width // 3)
        window_height = max(1, source_height // 3)

        flags = pygame.OPENGL | pygame.DOUBLEBUF
        try:
            pygame.display.set_mode((window_width, window_height), pygame.OPENGL | pygame.DOUBLEBUF, vsync=0)
        except TypeError:
            pygame.display.set_mode((window_width, window_height), pygame.OPENGL | pygame.DOUBLEBUF, vsync=0)

        pygame.display.set_caption("Screen Blur")

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

        copy_program = create_program(VERTEX_SHADER, COPY_FRAGMENT_SHADER)
        blur_program = create_program(VERTEX_SHADER, BLUR_FRAGMENT_SHADER)
        vao, vbo, ebo = create_fullscreen_quad()

        capture_texture = create_texture(source_width, source_height, GL_BGRA)
        ping_texture = create_texture(window_width, window_height, GL_RGBA)
        pong_texture = create_texture(window_width, window_height, GL_RGBA)
        ping_fbo = create_framebuffer(ping_texture)
        pong_fbo = create_framebuffer(pong_texture)

        glActiveTexture(GL_TEXTURE0)

        glUseProgram(copy_program)
        glUniform1i(glGetUniformLocation(copy_program, "uTexture"), 0)

        glUseProgram(blur_program)
        glUniform1i(glGetUniformLocation(blur_program, "uTexture"), 0)
        direction_uniform = glGetUniformLocation(blur_program, "uDirection")

        texel_x = 1.0 / float(window_width)
        texel_y = 1.0 / float(window_height)

        clock = pygame.time.Clock()
        frame_counter = 0
        fps_start = time.perf_counter()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

            frame = capture.grab(monitor)
            glBindTexture(GL_TEXTURE_2D, capture_texture)
            glTexSubImage2D(
                GL_TEXTURE_2D,
                0,
                0,
                0,
                source_width,
                source_height,
                GL_BGRA,
                GL_UNSIGNED_BYTE,
                frame.bgra,
            )

            glBindFramebuffer(GL_FRAMEBUFFER, ping_fbo)
            glViewport(0, 0, window_width, window_height)
            glUseProgram(copy_program)
            glBindTexture(GL_TEXTURE_2D, capture_texture)
            draw_fullscreen(vao)

            glUseProgram(blur_program)
            for _ in range(BLUR_PASSES):
                glBindFramebuffer(GL_FRAMEBUFFER, pong_fbo)
                glBindTexture(GL_TEXTURE_2D, ping_texture)
                glUniform2f(direction_uniform, texel_x, 0.0)
                draw_fullscreen(vao)

                glBindFramebuffer(GL_FRAMEBUFFER, ping_fbo)
                glBindTexture(GL_TEXTURE_2D, pong_texture)
                glUniform2f(direction_uniform, 0.0, texel_y)
                draw_fullscreen(vao)

            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            glViewport(0, 0, window_width, window_height)
            glUseProgram(copy_program)
            glBindTexture(GL_TEXTURE_2D, ping_texture)
            draw_fullscreen(vao)

            pygame.display.flip()
            clock.tick(TARGET_FPS)

            frame_counter += 1
            now = time.perf_counter()
            elapsed = now - fps_start
            if elapsed >= 1.0:
                fps = frame_counter / elapsed
                pygame.display.set_caption(
                    f"Screen Blur - {window_width}x{window_height} - {fps:.1f} FPS"
                )
                fps_start = now
                frame_counter = 0

        glDeleteTextures([capture_texture, ping_texture, pong_texture])
        glDeleteFramebuffers(2, [ping_fbo, pong_fbo])
        glDeleteBuffers(1, [vbo])
        glDeleteBuffers(1, [ebo])
        glDeleteVertexArrays(1, [vao])
        glDeleteProgram(copy_program)
        glDeleteProgram(blur_program)

    pygame.quit()


if __name__ == "__main__":
    main()
