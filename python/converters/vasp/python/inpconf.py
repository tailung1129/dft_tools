r"""
  Module for parsing and checking an input config-file.
"""

import ConfigParser
import numpy as np
import re
import sys
import itertools as it
import vaspio

def issue_warning(message):
    """
    Issues a warning.
    """
    print
    print "  !!! WARNING !!!: " + message
    print

################################################################################
################################################################################
#
# class ConfigParameters
#
################################################################################
################################################################################
class ConfigParameters:
    r"""
    Class responsible for parsing of the input config-file.
  
    Parameters:

    - *sh_required*, *sh_optional* : required and optional parameters of shells
    - *gr_required*, *gr_optional* : required and optional parameters of groups

    The dictionary contains a mapping of conf-file keywords to
    a pair of objects:

      1. internal name of a parameter
      2. function used to convert an input string into data for a given parameter
    """
################################################################################
#
# __init__()
#
################################################################################
    def __init__(self, input_filename, verbosity=1):
        self.verbosity = verbosity
        self.cp = ConfigParser.SafeConfigParser()
        self.cp.readfp(open(input_filename, 'r'))

        self.parameters = {}

        self.sh_required = {
            'ions': ('ion_list', self.parse_string_ion_list),
            'lshell': ('lshell', int)}

        self.sh_optional = {
            'rtransform': ('tmatrix', lambda s: self.parse_string_tmatrix(s, real=True)),
            'ctransform': ('tmatrix', lambda s: self.parse_string_tmatrix(s, real=False))}

        self.gr_required = {
            'shells': ('shells', lambda s: map(int, s.split())),
            'emin': ('emin', float),
            'emax': ('emax', float)}

        self.gr_optional = {
            'normalize' : ('normalize', self.parse_string_logical),
            'normion' : ('normion', self.parse_string_logical)}



#
# Special parsers
#
################################################################################
#
# parse_string_ion_list()
#
################################################################################
    def parse_string_ion_list(self, par_str):
        """
        The ion list accepts two formats:
          1). A list of ion indices according to POSCAR.
              The list can be defined as a range '9..20'.
          2). An element name, in which case all ions with
              this name are included.

        The second option requires an input from POSCAR file.
        """
# First check if a range is given
        patt = '([0-9]+)\.\.([0-9]+)'
        match = re.match(patt, par_str)
        if match:
            i1, i2 = tuple(map(int, match.groups()[:2]))
            mess = "First index of the range must be smaller or equal to the second"
            assert i1 <= i2, mess
            ion_list = np.array(range(i1 - 1, i2))
        else:
# Check if a set of indices is given
            try:
                l_tmp = map(int, par_str.split())
                l_tmp.sort()
# Subtract 1 so that VASP indices (starting with 1) are converted
# to Python indices (starting with 0)
                ion_list = np.array(l_tmp) - 1
            except ValueError:
                err_msg = "Only an option with a list of ion indices is implemented"
                raise NotImplementedError(err_msg)

        err_mess = "Lowest ion index is smaller than 1 in '%s'"%(par_str)
        assert np.all(ion_list >= 0), err_mess

        return ion_list

################################################################################
#
# parse_string_logical()
#
################################################################################
    def parse_string_logical(self, par_str):
        """
        Logical parameters are given by string 'True' or 'False'
        (case does not matter). In fact, only the first symbol matters so that
        one can write 'T' or 'F'.
        """
        first_char = par_str[0].lower()
        assert first_char in 'tf', "Logical parameters should be given by either 'True' or 'False'"
        return first_char == 't'

################################################################################
#
# parse_string_tmatrix()
#
################################################################################
    def parse_string_tmatrix(self, par_str, real):
        """
        Transformation matrix is defined as a set of rows separated
        by a new line symbol.
        """
        str_rows = par_str.split('\n')
        try:
            rows = [map(float, s.split()) for s in str_rows]
        except ValueError:
            err_mess = "Cannot parse a matrix string:\n%s"%(par_str)
            raise ValueError(err_mess)

        nr = len(rows)
        nm = len(rows[0])

        err_mess = "Number of columns must be the same:\n%s"%(par_str)
        for row in rows:
            assert len(row) == nm, err_mess

        if real:
            mat = np.array(rows)
        else:
            err_mess = "Complex matrix must contain 2*M values:\n%s"%(par_str)
            assert 2 * (nm / 2) == nm, err_mess

            tmp = np.array(rows, dtype=np.complex128)
            mat = tmp[:, 0::2] + 1.0j * tmp[:, 1::2]

        return mat

################################################################################
#
# parse_parameter_set()
#
################################################################################
    def parse_parameter_set(self, section, param_set, exception=False):
        """
        Parses required or optional parameter set from a section.
        For required parameters `exception=True` must be set.
        """
        parsed = {}
        for par in param_set.keys():
            try:
                par_str = self.cp.get(section, par)
            except ConfigParser.NoOptionError:
                if exception:
                    message = "Required parameter '%s' not found in section [%s]"%(par, section)
                    raise Exception(message)
                else:
                    continue

            if self.verbosity > 0:
                print "  %s = %s"%(par, par_str)

            key = param_set[par][0]
            parse_fun = param_set[par][1]
            parsed[key] = parse_fun(par_str)

        return parsed


################################################################################
#
# parse_shells()
#
################################################################################
    def parse_shells(self):
        """
        Parses all [Shell] sections.
        """
# Find all [Shell] sections
# (note that ConfigParser transforms all names to lower case)
        sections = self.cp.sections()

        sh_patt1 = re.compile('shell +.*', re.IGNORECASE)
        sec_shells = filter(sh_patt1.match, sections)

        self.nshells = len(sec_shells)
        assert self.nshells > 0, "No projected shells found in the input file"

        if self.verbosity > 0:
            print
            if self.nshells > 1:
                print "  Found %i projected shells"%(self.nshells)
            else:
                print "  Found 1 projected shell"

# Get shell indices
        sh_patt2 = re.compile('shell +([0-9]*)$', re.IGNORECASE)
        try:
            get_ind = lambda s: int(sh_patt2.match(s).groups()[0])
            sh_inds = map(get_ind, sec_shells)
        except (ValueError, AttributeError):
            raise ValueError("Failed to extract shell indices from a list: %s"%(sec_shells))

        self.sh_sections = {ind: sec for ind, sec in it.izip(sh_inds, sec_shells)}

# Check that all indices are unique
# In principle redundant because the list of sections will contain only unique names
        assert len(sh_inds) == len(set(sh_inds)), "There must be no shell with the same index!"

# Ideally, indices should run from 1 to <nshells>
# If it's not the case, issue a warning
        sh_inds.sort()
        if sh_inds != range(1, len(sh_inds) + 1):
            issue_warning("Shell indices are not uniform or not starting from 1. "
               "This might be an indication of a incorrect setup.")

# Parse shell parameters and put them into a list sorted according to the original indices
        self.shells = []
        for ind in sh_inds:
            shell = {}
# Store the original user-defined index
            shell['user_index'] = ind
            section = self.sh_sections[ind]

# Shell required parameters
            if self.verbosity > 0:
                print
                print "  Required shell parameters:"
            parsed = self.parse_parameter_set(section, self.sh_required, exception=True)
            shell.update(parsed)

# Shell optional parameters
            if self.verbosity > 0:
                print
                print "  Optional shell parameters:"
            parsed = self.parse_parameter_set(section, self.sh_optional, exception=False)
            shell.update(parsed)

# Group required parameters
# Must be given if no group is explicitly specified
# If in conflict with the [Group] section, the latter has a priority
            if self.verbosity > 0:
                print
                print "  Required group parameters:"
            parsed = self.parse_parameter_set(section, self.gr_required, exception=False)
            shell.update(parsed)

# Group optional parameters
            if self.verbosity > 0:
                print
                print "  Optional group parameters:"
            parsed = self.parse_parameter_set(section, self.gr_optional, exception=False)
            shell.update(parsed)

            self.shells.append(shell)

################################################################################
#
# parse_groups()
#
################################################################################
    def parse_groups(self):
        """
        Parses [Group] sections.
        """
# Find group sections
        sections = self.cp.sections()

        gr_patt = re.compile('group +(.*)', re.IGNORECASE)
        sec_groups = filter(gr_patt.match, sections)

        self.ngroups = len(sec_groups)

        self.groups = []
# Parse group parameters
        for section in sec_groups:
            group = {}

# Extract group index (FIXME: do we really need it?)
            gr_patt2 = re.compile('group +([0-9]*)$', re.IGNORECASE)
            try:
                gr_ind = int(gr_patt2.match(section).groups()[0])
            except (ValueError, AttributeError):
                raise ValueError("Failed to extract group index from a group name: %s"%(section))
            group['index'] = gr_ind

# Group required parameters
            if self.verbosity > 0:
                print
                print "  Required group parameters:"
            parsed = self.parse_parameter_set(section, self.gr_required, exception=True)
            group.update(parsed)

# Group optional parameters
            if self.verbosity > 0:
                print
                print "  Optional group parameters:"
            parsed = self.parse_parameter_set(section, self.gr_optional, exception=False)
            group.update(parsed)

            self.groups.append(group)

# Sort groups according to indices defined in the config-file
        if self.ngroups > 0:
            self.groups.sort(key=lambda g: g['index'])

################################################################################
#
# groups_shells_consistency()
#
################################################################################
    def groups_shells_consistency(self):
        """
        Ensures consistency between groups and shells.
        In particular:
        - if no groups are explicitly defined and only shell is defined create
          a group automatically
        - check the existance of all shells referenced in the groups
        - check that all shells are referenced in the groups
        """
# Special case: no groups is defined
        if self.ngroups == 0:
# Check that 'nshells = 1'
            assert self.nshells == 1, "At least one group must be defined if there are more than one shells."

# Otherwise create a single group taking group information from [Shell] section
            self.groups.append({})
# Check that the single '[Shell]' section contains enough information
# and move it to the `groups` dictionary
            try:
                for par in self.gr_required.keys():
                    key = self.gr_required[par][0]
                    value = self.shells[0].pop(key)
                    self.groups[0][key] = value
            except KeyError:
                message = "One [Shell] section is specified but no explicit [Group] section is provided."
                message += " In this case the [Shell] section must contain all required group information.\n"
                message += "  Required parameters are: %s"%(self.gr_required.keys())
                raise KeyError(message)

# Do the same for optional group parameters, but do not raise an exception
            for par in self.gr_optional.keys():
                try:
                    key = self.gr_optional[par][0]
                    value = self.shells[ind].pop(key)
                    self.groups[0][key] = value
                except KeyError:
                    continue
# Add the index of the single shell into the group                
            self.groups.update({'shells': 0})

#
# Consistency checks
#
# Check the existance of shells referenced in the groups 
        def find_shell_by_user_index(uindex):
            for ind, shell in enumerate(self.shells):
                if shell['user_index'] == uindex:
                    return shell
            raise KeyError

        sh_inds = []
        for group in self.groups:
            gr_shells = group['shells']
            for user_ind in gr_shells:
                try:
                    ind, shell = find_shell_by_user_index(user_ind)
                except KeyError:
                    raise Exception("Shell %i reference in group '%s' does not exist"%(user_ind, group['index'])
                sh_inds.append(ind)

# If [Shell] section contains (potentiall conflicting) group parameters
# remove them and issue a warning
# First, required group parameters
                for par in self.gr_required.keys():
                    try:
                        key = self.gr_required[par][0]
                        value = shell.pop(key)
                        mess = ("  Redundant group parameter '%s' in [Shell] section"
                                " %i is discarded"%(par, user_ind))
                        issue_warning(mess)
                    except KeyError:
                        continue

# Second, optional group parameters
                for par in self.gr_optional.keys():
                    try:
                        key = self.gr_optional[par][0]
                        value = shell.pop(key)
                        mess = ("  Redundant group parameter '%s' in [Shell] section"
                                " %i is discarded"%(par, user_ind))
                        issue_warning(mess)
                    except KeyError:
                        continue

        sh_refs_used = list(set(sh_inds))
        sh_refs_used.sort()

# Check that all shells are referenced in the groups
        assert sh_refs_used == range(self.nshells), "Some shells are not inside any of the groups"

 

################################################################################
#
# Main parser
# parse_logical()
#
################################################################################
    def parse_input(self):
        """
        Parses input conf-file.
        """
        self.parse_shells()
        self.parse_groups()

        self.groups_shells_consistency()

# Return a 
        output_pars = [{} for isec in xrange(nsections)]
        for isec, section in enumerate(sections):
            print "Section: %s"%(section)
            for par in required.keys():
                try:
                    par_str = cp.get(section, par)
                except ConfigParser.NoOptionError:
                    raise SystemExit("*** Error: Required entry '%s' not found in the input file"%(par))

                print "  %s: %s"%(par, par_str)
                key = required[par][0]
                parse_fun = required[par][1]
                output_pars[isec][key] = parse_fun(par_str)

        print output_pars
        print cp.get(section, 'rtransform').strip().split('\n')

        return output_pars

if __name__ == '__main__':
    narg = len(sys.argv)
    if narg < 2:
        raise SystemExit("  Usage: python pyconf.py <conf-file> [<path-to-vasp-calcultaion>]")
    else:
        filename = sys.argv[1]
        if narg > 2:
            vasp_dir = sys.argv[2]
            if vasp_dir[-1] != '/':
                vasp_dir += '/'
        else:
            vasp_dir = './'


#    plocar = vaspio.Plocar()
#    plocar.from_file(vasp_dir)
#    poscar = vaspio.Poscar()
#    poscar.from_file(vasp_dir)
#    kpoints = vaspio.Kpoints()
#    kpoints.from_file(vasp_dir)
    eigenval = vaspio.Eigenval()
    eigenval.from_file(vasp_dir)
    doscar = vaspio.Doscar()
    doscar.from_file(vasp_dir)
#    pars = parse_input(filename)

