# Runs kALDo on crystal silicon using force constants calculated on a variable
# number of k-points in Quantum Espresso (aka how many images).
#
# Usage: python 1_run_kaldo.py <replicas_per_axis> <u/n> <disp> <overwrite>
# u/n controls if kALDo unfolds the force constants
# disp will exit the calculations after making a dispersion
# overwrite allows the script to replace data written in previous runs
#
# WARNING: Please note, that crystal silicon is sometimes represented with
# atoms at negative coordinates ((0,0,0)+(-1/4, 1/4, 1/4)) but shengbte forces
# it to be represented as ((0,0,0)+(1/4, 1/4, 1/4)). Similar differences in
# representation across interfaces will result in unphysical output from kALDo

# Harmonic ----------------------
# Dispersion args
npoints = 150 # points along path
pathstring = 'GXULG' # actual path

# Anharmonic --------------------
# Threading per process
nthread = 2
# K-pt grid
k = 7 # cubed
# Conductivity method
cond_method = 'inverse'

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# You shouldn't need to edit below this line, but it should be well commented
# so that you can reference it for how to set up your own workflow
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
### Settings detected by environment variables, POSCARs and arguments
import os
import sys
import numpy as np
from ase.io import read
# Replicas
nrep = int(sys.argv[1][0])
inp_folder = os.environ["kaldo_inputs"]
supercell, fcs_folder = np.array([nrep, nrep, nrep]), inp_folder+'/{}x{}x{}'.format(nrep, nrep, nrep)
kpts, kptfolder = [k, k, k], '{}_{}_{}'.format(k,k,k)
third_supercell = np.array([3,3,3])
# Detect unfolding
unfold_bool = False
unfold = 'n'
if 'u' in sys.argv[1]:
    unfold_bool = True
    unfold = 'u'
# Detect harmonic
harmonic = False
if 'harmonic' in sys.argv:
    harmonic = True
# Control data IO + overwriting controls
overwrite = False;
prefix = os.environ['kaldo_ald']
ald_folder = prefix+'/{}{}'.format(nrep, unfold)
if 'overwrite' in sys.argv:
    overwrite = True
if os.path.isdir(prefix):
    print('\n!! - '+prefix+' directory already exists')
    if os.path.isdir(ald_folder):
        print('!! - '+ald_folder+' directory already exists')
        print('!! - continuing may overwrite, or load previous data\n')
        if not overwrite:
            print('!! - overwrites disallowed, exiting safely..')
            exit()
else:
    os.mkdir(prefix)
# Control threading behavior
os.environ['CUDA_VISIBLE_DEVICES']=" "
import tensorflow as tf
tf.config.threading.set_inter_op_parallelism_threads(nthread)
tf.config.threading.set_intra_op_parallelism_threads(nthread)


# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
### Print out detected settings
print('\n\n\tCalculating for supercell {}x{}x{} -- '.format(nrep, nrep, nrep))
print('\t\t Unfolding (u/n): {}'.format(unfold))
print('\t\t In folder:       {}'.format(fcs_folder))
print('\t\t Out folder:      {}'.format(ald_folder))
print('\t\t Dispersion only: {}'.format(harmonic))
print('\t\t Overwrite permission: {}\n\n'.format(overwrite))
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
### Begin simulation
# Import kALDo
from kaldo.forceconstants import ForceConstants
from kaldo.phonons import Phonons
from kaldo.conductivity import Conductivity
from kaldo.controllers.plotter import plot_dispersion

# Create kALDo objects
forceconstant = ForceConstants.from_folder(
                       folder=fcs_folder,
                       supercell=supercell,
                       only_second=harmonic,
                       third_supercell=third_supercell,
                       is_acoustic_sum=True,
                       format='shengbte-qe')
#if unfold: # unfold the third order force constants too
#    unfolded_third = forceconstant.unfold_third_order(distance_threshold=4)
#    forceconstant.third.value = unfolded_third
phonons = Phonons(forceconstants=forceconstant,
              kpts=kpts,
              is_classic=False,
              temperature=300,
              folder=ald_folder,
              is_unfolding=unfold_bool,
              storage='numpy')

# Harmonic data along path
# Although you need to specify the k-pt grid for the Phonons object, we don't
# actually use it for dispersion relations and velocities the sampling is taken
# care of by the path specified and the npoints variable set above.
# Note: Choice of k-pt grid WILL effect DoS calculations for amorphous models.
atoms = read(inp_folder+'/3x3x3/POSCAR', format='vasp')
cell = atoms.cell
lat = cell.get_bravais_lattice()
path = cell.bandpath(pathstring, npoints=npoints)
print('Unit cell detected: {}'.format(atoms))
print('Special points on cell:')
print(lat.get_special_points())
print('Path: {}'.format(path))
plot_dispersion(phonons, is_showing=False,
            manually_defined_path=path, folder=ald_folder+'/dispersion')
if harmonic:
    print('\n\n\n\tHarmonic quantities generated, exiting safely ..')
    quit(0)

# Conductivity & Anharmonics
# Different methods of calculating the conductivity can be compared
# but full inversion of the three-phonon scattering matrix typically agrees with
# experiment more than say the relaxation time approximation (not applicable for
# systems without symmetry).
# Calculating this K will produce as a byproduct things like the phonon
# bandwidths, phase space etc, but some need to be explicitly called to output
# numpy files (e.g. Phonons.participation_ratio, find more in Phonons docs).
#
# All of the anharmonic quantities should be converged according to a sensitivity
# analysis of their value against increasing k-points.
cond = Conductivity(phonons=phonons, method=cond_method, storage='numpy')
cond_matrix = cond.conductivity.sum(axis=0)
diag = np.diag(cond_matrix)
offdiag = np.abs(cond_matrix).sum() - np.abs(diag).sum()
print('Conductivity from full inversion (W/m-K):\n%.3f' % (np.mean(diag)))
print('Sum of off-diagonal terms: %.3f' % offdiag)
print('Full matrix:')
print(cond_matrix)
