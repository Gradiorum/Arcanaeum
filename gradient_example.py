import numpy as np
import matplotlib.pyplot as plt

# Define f(x, y)
def f(x, y):
    return x**2 + y**2

# Define grad f(x, y)
def grad_f(x, y):
    return np.array([2*x, 2*y])

# Create a meshgrid for visualization
x_vals = np.linspace(-3, 3, 30)
y_vals = np.linspace(-3, 3, 30)
X, Y = np.meshgrid(x_vals, y_vals)
Z = f(X, Y)

# Plot contours of f
plt.figure(figsize=(8,6))
contours = plt.contour(X, Y, Z, levels=15)
plt.clabel(contours, inline=True)

# Show gradient vectors at a few sample points
sample_points = [(-2, -2), (-2, 2), (2, -2), (2, 2), (1, 1)]
for (x0, y0) in sample_points:
    g = grad_f(x0, y0)
    plt.arrow(x0, y0, 0.4*g[0], 0.4*g[1], 
              head_width=0.15, head_length=0.2, color='red')

plt.title("Contours of f(x,y)=x^2 + y^2 and sample gradient vectors")
plt.xlabel("x")
plt.ylabel("y")
plt.axis('equal')
plt.show()
