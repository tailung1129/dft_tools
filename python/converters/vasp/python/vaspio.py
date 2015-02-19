
import numpy as np
import plocar_io.c_plocar_io as c_plocar_io

def read_lines(filename):
    r"""
    Generator of lines for a file

    Parameters
    ----------

    filename (str) : name of the file
    """
    with open(filename, 'r') as f:
        for line in f:
            yield line

################################################################################
################################################################################
#
# class VaspData
#
################################################################################
################################################################################
class VaspData:
    """
    Container class for all VASP data.
    """
    def __init__(self, vasp_dir):
        self.vasp_dir = vasp_dir

        self.plocar = Plocar()
        self.plocar.from_file(vasp_dir)
        self.poscar = Poscar()
        self.poscar.from_file(vasp_dir)
        self.kpoints = Kpoints()
        self.kpoints.from_file(vasp_dir)
        self.eigenval = Eigenval()
        self.eigenval.from_file(vasp_dir)
        self.doscar = Doscar()
        self.doscar.from_file(vasp_dir)

################################################################################
################################################################################
#
# class Plocar
#
################################################################################
################################################################################
class Plocar:
    r"""
    Class containing raw PLO data from VASP.

    Properties
    ----------

    plo (numpy.array((nion, ns, nk, nb, nlmmax))) : raw projectors
    """

    def from_file(self, vasp_dir='./', plocar_filename='PLOCAR'):
        r"""
        Reads non-normalized projectors from a binary file (`PLOCAR' by default)
        generated by VASP PLO interface.

        Parameters
        ----------

        vasp_dir (str) : path to the VASP working directory [default = `./']
        plocar_filename (str) : filename [default = `PLOCAR']

        """
# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        self.params, self.plo, self.ferw = c_plocar_io.read_plocar(vasp_dir + plocar_filename)


################################################################################
################################################################################
#
# class Poscar
#
################################################################################
################################################################################
class Poscar:
    """
    Class containing POSCAR data from VASP.

    Properties
    ----------

      nq (int) : total number of ions
      ntypes ([int]) : number of ion types
      nions (int) : a list of number of ions of each type
      a_brav (numpy.array((3, 3), dtype=float)) : lattice vectors
      q_types ([numpy.array((nions, 3), dtype=float)]) : a list of
          arrays each containing fractional coordinates of ions of a given type
    """
    def __init__(self):
        self.q_cart = None
        self.b_rec = None

    def from_file(self, vasp_dir='./', poscar_filename='POSCAR'):
        """
        Reads POSCAR and returns a dictionary.

        Parameters
        ----------

        vasp_dir (str) : path to the VASP working directory [default = `./']
        plocar_filename (str) : filename [default = `PLOCAR']

        """
# Convenince local function
        def readline_remove_comments():
            return f.next().split('!')[0].strip()

# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        f = read_lines(vasp_dir + poscar_filename)
# Comment line
        comment = f.next().rstrip()
        print "  Found POSCAR, title line: %s"%(comment)

# Read scale
        sline = readline_remove_comments()
        ascale = float(sline[0])
# Read lattice vectors
        self.a_brav = np.zeros((3, 3))
        for ia in xrange(3):
            sline = readline_remove_comments()
            self.a_brav[ia, :] = map(float, sline.split())
# Negative scale means that it is a volume scale
        if ascale < 0:
            vscale = -ascale
            vol = np.linalg.det(self.a_brav)
            ascale = (vscale / vol)**(1.0/3)

        self.a_brav *= ascale

# Depending on the version of VASP there could be
# an extra line with element names
        sline = readline_remove_comments()
        try:
# Old v4.6 format: no element names
            self.nions = map(int, sline.split())
            self.el_names = ['El%i'%(i) for i in xrange(len(nions))]
        except ValueError:
# New v5.x format: read element names first
            self.el_names = sline.split()
            sline = readline_remove_comments()
            self.nions = map(int, sline.split())

# Set the number of atom sorts (types) and the total
# number of atoms in the unit cell
        self.ntypes = len(self.nions)
        self.nq = sum(self.nions)

# Check for the line 'Selective dynamics' (and ignore it)
        sline = readline_remove_comments()
        if sline[0].lower() == 's':
            sline = readline_remove_comments()

# Check whether coordinates are cartesian or fractional
        cartesian = (sline[0].lower() in 'ck')
        if cartesian:
            brec = np.linalg.inv(self.a_brav.T)

# Read atomic positions
        self.q_types = []
        for it in xrange(self.ntypes):
            q_at_it = np.zeros((self.nions[it], 3))
            for iq in xrange(self.nions[it]):
                sline = readline_remove_comments()
                qcoord = map(float, sline.split()[:3])
                if cartesian:
                    qcoord = np.dot(brec, qcoord)
                q_at_it[iq, :] = qcoord

            self.q_types.append(q_at_it)

        print "  Total number of ions:", self.nq
        print "  Number of types:", self.ntypes
        print "  Number of ions for each type:", self.nions

#        print
#        print "  Coords:"
#        for it in xrange(ntypes):
#            print "    Element:", el_names[it]
#            print q_at[it]

################################################################################
################################################################################
#
# class Kpoints
#
################################################################################
################################################################################
class Kpoints:
    """
    Class describing k-points and optionally tetrahedra.

    Properties
    ----------

        nktot (int) : total number of k-points in the IBZ
        kpts (numpy.array((nktot, 3), dtype=float)) : k-point vectors (fractional coordinates)
        ntet (int) : total number of k-point tetrahedra
        itet (numpy.array((ntet, 5), dtype=float) : array of tetrahedra
        volt (float) : volume of a tetrahedron (the k-grid is assumed to
          be uniform)
    """
#
# Reads IBZKPT file
#
    def from_file(self, vasp_dir='./', ibz_filename='IBZKPT'):
        """
        Reads from IBZKPT: k-points and optionally
        tetrahedra topology (if present).

        Parameters
        ----------

        vasp_dir (str) : path to the VASP working directory [default = `./']
        plocar_filename (str) : filename [default = `PLOCAR']

        """

# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        ibz_file = read_lines(vasp_dir + ibz_filename)

#   Skip comment line
        line = ibz_file.next()
#   Number of k-points
        line = ibz_file.next()
        self.nktot = int(line.strip().split()[0])

        print
        print "   {0:>26} {1:d}".format("Total number of k-points:", self.nktot)

        self.kpts = np.zeros((self.nktot, 3))

#   Skip comment line
        line = ibz_file.next()
        for ik in xrange(self.nktot):
            line = ibz_file.next()
            self.kpts[ik, :] = map(float, line.strip().split()[:3])
        
# Attempt to read tetrahedra
#   Skip comment line ("Tetrahedra")
        try:
            line = ibz_file.next()

#   Number of tetrahedra and volume = 1/(6*nkx*nky*nkz)
            line = ibz_file.next()
            sline = line.split()
            self.ntet = int(sline[0])
            self.volt = float(sline[1])

            print "   {0:>26} {1:d}".format("Total number of tetrahedra:", self.ntet)

#   Traditionally, itet[it, 0] contains multiplicity
            self.itet = np.zeros((self.ntet, 5), dtype=int)
            for it in xrange(self.ntet):
               line = ibz_file.next()
               self.itet[it, :] = map(int, line.split()[:5])
        except StopIteration, ValueError:
            print "  No tetrahedron data found in %s. Skipping..."%(ibz_filename)
            self.ntet = 0

#        data = { 'nktot': nktot,
#                 'kpts': kpts,
#                 'ntet': ntet,
#                 'itet': itet,
#                 'volt': volt }
#
#        return data


################################################################################
################################################################################
#
# class Eigenval
#
################################################################################
################################################################################
class Eigenval:
    """
    Class containing Kohn-Sham-eigenvalues data from VASP (EIGENVAL file).
    """
    def from_file(self, vasp_dir='./', eig_filename='EIGENVAL'):
        """
        Reads eigenvalues from EIGENVAL. Note that the file also
        contains k-points with weights. They are also stored and
        then used to check the consistency of files read.
        """

# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        f = read_lines(vasp_dir + eig_filename)

# First line: only the first and the last number out of four
# are used; these are 'nions' and 'ispin'
        sline = f.next().split()
        self.nq = int(sline[0])
        self.ispin = int(sline[3])

# Second line: cell volume and lengths of lattice vectors (skip)
        sline = f.next()

# Third line: temperature (skip)
        sline = f.next()

# Fourth and fifth line: useless
        sline = f.next()
        sline = f.next()

# Sixth line: NELECT, NKTOT, NBTOT
        sline = f.next().split()
        self.nelect = int(sline[0])
        self.nktot = int(sline[1])
        self.nband = int(sline[2])

# Set of eigenvalues and k-points
        self.kpts = np.zeros((self.nktot, 3))
        self.kwghts = np.zeros((self.nktot,))
        self.eigs = np.zeros((self.nktot, self.nband, self.ispin))

        for ik in xrange(self.nktot):
            sline = f.next() # Empty line
            sline = f.next() # k-point info
            tmp = map(float, sline.split())
            self.kpts[ik, :] = tmp[:3]
            self.kwghts[ik] = tmp[3]

            for ib in xrange(self.nband):
                sline = f.next().split()
                tmp = map(float, sline[1:self.ispin+1])
                self.eigs[ik, ib, :] = tmp[:]
                

################################################################################
################################################################################
#
# class Doscar
#
################################################################################
################################################################################
class Doscar:
    """
    Class containing some data from DOSCAR
    """
    def from_file(self, vasp_dir='./', dos_filename='DOSCAR'):
        """
        Reads only E_Fermi from DOSCAR.
        """

# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        f = read_lines(vasp_dir + dos_filename)

# Skip first 5 lines
        for _ in xrange(5):
            sline = f.next()

# Sixth line: EMAX, EMIN, NEDOS, EFERMI, 1.0
        sline = f.next().split()
        self.efermi = float(sline[3])


################################################################
#
# Reads SYMMCAR
#
################################################################
def read_symmcar(vasp_dir, symm_filename='SYMMCAR'):
    """
    Reads SYMMCAR.
    """
#   Shorthand for simple parsing
    def extract_int_par(parname):
        return int(re.findall(parname + '\s*=\s*(\d+)', line)[-1])

# Add a slash to the path name if necessary
    if vasp_dir[-1] != '/':
        vasp_dir += '/'

    symmcar_exist = False
    sym_file = read_lines(vasp_dir + symm_filename)
    line = sym_file.next()
    nrot = extract_int_par('NROT')

    line = sym_file.next()
    ntrans = extract_int_par('NPCELL')
#   Lmax
    line = sym_file.next()
    lmax = extract_int_par('LMAX')
    mmax = 2 * lmax + 1
#   Nion
    line = sym_file.next()
    nion = extract_int_par('NION')

    print "   {0:>26} {1:d}".format("Number of rotations:", nrot)
    print "   {0:>26} {1:d}".format("Number of translations:", ntrans)
    print "   {0:>26} {1:d}".format("Number of ions:", nion)
    print "   {0:>26} {1:d}".format("L_max:", lmax)

    rot_mats = np.zeros((nrot, lmax+1, mmax, mmax))
    rot_map = np.zeros((nrot, ntrans, nion), dtype=np.int32)

    for irot in xrange(nrot):
#   Empty line
        line = sym_file.next()
#   IROT index (skip it)
        line = sym_file.next()
#   ISYMOP matrix (can be also skipped)
        line = sym_file.next()
        line = sym_file.next()
        line = sym_file.next()

#   Skip comment "  Permutation map..."
        line = sym_file.next()
#   Permutations (in chunks of 20 indices per line)
        for it in xrange(ntrans):
            for ibl in xrange((nion - 1) / 20 + 1):
                i1 = ibl * 20
                i2 = (ibl + 1) * 20
                line = sym_file.next()
                rot_map[irot, it, i1:i2] = map(int, line.split())

            for l in xrange(lmax + 1):
                mmax = 2 * l + 1
#   Comment: "L = ..."
            line = sym_file.next()
            for m in xrange(mmax):
                line = sym_file.next()
                rot_mats[irot, l, m, :mmax] = map(float, line.split()[:mmax])

    data.update({ 'nrot': nrot, 'ntrans': ntrans,
                  'lmax': lmax, 'nion': nion,
                  'sym_rots': rot_mats, 'perm_map': rot_map })


