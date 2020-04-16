from potential_field_metric import PotentialFieldPlanner, draw_heatmap, load_image

import numpy as np
import scipy.ndimage
import matplotlib.pyplot as plt
import cv2
from IPython import embed
import time
import os
import timeit

# Parameters
# AREA_WIDTH = 0.0  # potential area width [m]
KP = 1.0            # attractive potential gain
ETA = 1000.0        # repulsive potential gain
ETA2 = 500.0
MIN_DISTANCE = 0.1
MIN_OBSTACLE_DISTANCE = 5.0
DESIRED_DISTANCE = 10
MAX_OBSTACLE_DISTANCE = 50
MAX_POTENTIAL = 5

show_animation = False
show_result = True


class PotentialFieldPlannerGrid(PotentialFieldPlanner):
    #override
    def set_problem(self, grid, sx, sy, gx, gy, ox, oy, resolution, use_goal_field, use_start_field, use_obstacle_field):
        self.grid = grid
        self.use_goal_field = use_goal_field
        self.use_start_field = use_start_field
        self.use_obstacle_field = use_obstacle_field
        self.sx = sx
        self.sy = sy
        self.gx = gx
        self.gy = gy
        # self.ox = ox
        # self.oy = oy
        self.resolution = resolution

        # transform to indices
        self.minx = 0
        self.miny = 0
        self.maxx = self.grid.shape[0]
        self.maxy = self.grid.shape[1]

        self.xw = self.grid.shape[0]
        self.yw = self.grid.shape[1]

        self.sx_id = (sx - self.minx) / resolution
        self.sy_id = (sy - self.miny) / resolution
        self.gx_id = (gx - self.minx) / resolution
        self.gy_id = (gy - self.miny) / resolution
        # self.ox_id = ox
        # self.oy_id = oy

        if self.sx_id < self.minx or self.sx_id >= self.maxx or self.gx_id < self.minx or self.gx_id >= self.maxx:
            print "start or goal exceed grid dimensions!"
            return False

        print ("start id: {} , {}".format(self.sx_id, self.sy_id))
        print ("goal id: {} , {}".format(self.gx_id, self.gy_id))
        # print ("ox id: {}".format(self.ox_id))
        # print ("oy id: {}".format(self.oy_id))
        print ("minx : {}".format(self.minx))
        print ("miny : {}".format(self.miny))
        print ("maxx : {}".format(self.maxx))
        print ("maxy : {}".format(self.maxy))
        return True

    def set_motion_model(self, motion_model):
        self.motion_model = motion_model

    def calc_potential_field(self):
        start = time.time()
        self.potential = np.zeros((self.xw, self.yw))
        print ("potential size: {}".format(self.potential.shape))

        # dist = scipy.spatial.distance.cdist(a,b)

        distance_array = scipy.ndimage.distance_transform_edt(self.grid)
        if self.use_obstacle_field:
            uo = self.repulsive_potential(distance_array)
            self.potential += uo

        if self.use_goal_field:
            self.potential += self.calc_attractive_potential()

        if self.use_start_field:
            self.potential += self.calc_start_repulsive_potential()

        end = time.time()
        print ("Caulculate potential time: {} s".format((end - start)))

        if show_animation:
            draw_heatmap(self.potential)
            # for stopping simulation with the esc key.
            plt.gcf().canvas.mpl_connect('key_release_event', lambda event: [
                exit(0) if event.key == 'escape' else None])
            plt.plot(self.sx_id, self.sy_id, "*k")
            plt.plot(self.gx_id, self.gy_id, "*m")

        return self.potential

    def repulsive_potential(self, d):
        conds = [d <= MIN_OBSTACLE_DISTANCE, (d > MIN_OBSTACLE_DISTANCE) & (d <= MAX_OBSTACLE_DISTANCE),
                 d > MAX_OBSTACLE_DISTANCE]
        funcs = [lambda x: MAX_POTENTIAL, lambda x: 0.5 * ETA * (x**-1 - DESIRED_DISTANCE**-1) ** 2,
                 lambda x: 0.0]
        return np.minimum(np.piecewise(d, conds, funcs), MAX_POTENTIAL)

    def calc_attractive_potential(self):
        pot = np.zeros((self.xw, self.yw))

        for ix in range(self.xw):
            x = ix * self.resolution + self.minx
            for iy in range(self.yw):
                y = iy * self.resolution + self.miny
                pot[ix][iy] = self.attractive_potential(x, y, self.gx, self.gy)
        return pot

    def attractive_potential(self, x, y, gx, gy):
        return 0.5 * KP * np.hypot(x - gx, y - gy)

    def calc_start_repulsive_potential(self):
        pot = np.zeros((self.xw, self.yw))

        for ix in range(self.xw):
            x = ix * self.resolution + self.minx
            for iy in range(self.yw):
                y = iy * self.resolution + self.miny
                pot[ix][iy] = self.start_attractive_potential(x, y, self.sx, self.sy)
        return pot

    def start_attractive_potential(self, x, y, sx, sy):
        d = np.hypot(x - sx, y - sy)
        if d <= MIN_DISTANCE:
            d = MIN_DISTANCE
        return 0.5 * KP * (d**-1)


    def potential_field_planning(self):
        # search path
        d = np.hypot(self.sx - self.gx, self.sy - self.gy)
        # ix = round((sx - minx) / self.resolution)
        # iy = round((sy - miny) / self.resolution)
        # gix = round((gx - minx) / self.resolution)
        # giy = round((gy - miny) / self.resolution)
        ix = self.sx_id
        iy = self.sy_id

        if show_animation:
            draw_heatmap(self.potential)
            # for stopping simulation with the esc key.
            plt.gcf().canvas.mpl_connect('key_release_event', lambda event: [
                exit(0) if event.key == 'escape' else None])
            plt.plot(self.sx_id, self.sy_id, "*k")
            plt.plot(self.gx_id, self.gy_id, "*m")

        rx, ry = [self.sx], [self.sy]
        previous_id = [(None, None)] * 3

        while d >= self.resolution:
            minp = float("inf")
            minix, miniy = -1, -1
            for i, _ in enumerate(self.motion_model):
                inx = int(ix + self.motion_model[i][0])
                iny = int(iy + self.motion_model[i][1])
                if inx >= len(self.potential) or iny >= len(self.potential[0]) or inx < 0 or iny < 0:
                    p = float("inf")  # outside area
                    print ("outside potential!")
                else:
                    p = self.potential[inx][iny]
                if minp > p:
                    minp = p
                    minix = inx
                    miniy = iny
            ix = minix
            iy = miniy
            xp = ix * self.resolution + self.minx
            yp = iy * self.resolution + self.miny
            d = np.hypot(self.gx - xp, self.gy - yp)
            rx.append(xp)
            ry.append(yp)

            if ((None, None) not in previous_id and
                    (previous_id[0] == previous_id[1] or previous_id[1] == previous_id[2]
                        or previous_id[0] == previous_id[2])):
                print ("Oscillation detected!!!")
                print previous_id
                break

            # roll previous
            previous_id[0] = previous_id[1]
            previous_id[1] = previous_id[2]
            previous_id[2] = (ix, iy)

            if show_animation:
                plt.plot(ix, iy, ".r")
                plt.pause(0.001)

        print("Finish!!")

        return rx, ry

    def draw_potential_profile(self):
        d = np.linspace(0, 2*MAX_OBSTACLE_DISTANCE, 500)
        p = np.array(map(self.repulsive_potential, d))

        fig = plt.figure()
        plt.plot(d, p)
        plt.ylim(-20, MAX_POTENTIAL)

def main():
    print("potential_field_planning start")

    # define problem
    sx = 410.0  # start x position [m]
    sy = 100.0  # start y positon [m]
    gx = 120.0  # goal x position [m]
    gy = 300.0  # goal y position [m]
    resolution = 1.0  # potential grid size [m]
    robot_radius = 5.0  # robot radius [m]

    if robot_radius > DESIRED_DISTANCE:
        print "robot_radius > DESIRED_DISTANCE"
        return False

    grid, ox, oy = load_image('./curb_map.png')
    print ("grid size: {}".format(grid.shape))
    # print grid
    if ox is None:
        print "image could not be loaded"
        return False

    potential_planner = PotentialFieldPlannerGrid()
    if not potential_planner.set_problem(grid, sx, sy, gx, gy, ox, oy, resolution, False, True, True):
        return False

    # dx, dy
    motion = [[1, 0],
              [0, 1],
              [-1, 0],
              [0, -1],
              [-1, -1],
              [-1, 1],
              [1, -1],
              [1, 1]]

    potential_planner.set_motion_model(motion)

    potential_planner.draw_potential_profile()

    if show_animation or show_result:
        fig = plt.figure()
        plt.grid(True)
        plt.axis("equal")

    # calc potential field
    potential_planner.calc_potential_field()

    # path generation
    rx, ry = potential_planner.potential_field_planning()
    print len(rx)
    print len(ry)

    if show_result:
        draw_heatmap(potential_planner.potential)
        plt.plot(potential_planner.sx_id, potential_planner.sy_id, "*k")
        plt.plot(potential_planner.gx_id, potential_planner.gy_id, "*m")
        for i in range(len(rx)):
            plt.plot(rx[i], ry[i], ".r")

    if show_animation or show_result:
        plt.show()

    return True


if __name__ == '__main__':
    print(__file__ + " start!!")
    if main():
        print(__file__ + " Done!!")
    else:
        print(__file__ + " Failed!!")
