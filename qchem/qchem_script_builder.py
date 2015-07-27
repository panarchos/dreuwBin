# vi: set et ts=4 sw=4 sts=4:

# Python module to build a qchem jobscripts
# Copyright (C) 2015 Michael F. Herbst
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# A copy of the GNU General Public License can be found in the 
# file COPYING or at <http://www.gnu.org/licenses/>.

from queuing_system import jobscript_builder as jsb
from queuing_system import queuing_system_data as qd
from queuing_system import queuing_system_environment as qe
import os.path
import subprocess
import shared_utils_lib as utils

#########################################################
#-- General stuff --#
#####################

class QChemPathNotDeterminedError(Exception):
    def __init__(self):
        super().__init__()

def determine_qchem_path(version_string=None):
    """
        run the selection script and return the qchem path

        version_string: The string to pass to qchem-vselector as the 
        readily known version string

        raises a subprocess.CalledProcessError exception if there 
        is anything wrong.
    """
    selector_prog="qchem-vselector"

    try:
        if version_string is not None:
            byte_str = subprocess.check_output([selector_prog,"--version", version_string])
        else:
            byte_str = subprocess.check_output(selector_prog)
        return byte_str.decode(encoding='utf-8').strip()
    except subprocess.CalledProcessError as e:
        raise QChemPathNotDeterminedError(e.argv[0])
    except UnicodeDecodeError as e:
        raise QChemPathNotDeterminedError(e.argv[0])

#########################################################
#--  QChem 4.0  --#
#####ü#############

class v40_qchem_args():
    def __init__(self):
        self.infile=None #str, path to the Q-Chem input file
        self.outfile=None #str or None, Q-Chem Output filename
        self.save_flag=None #bool, should the -save option be passed to Q-Chem
        self.savedir=None #str or None, the directory to use as the qchem savedir
        self.np_flag=None #bool, should the -np option be passed to Q-Chem
        self.nt_flag=None #bool, should the -nt option be passed to Q-Chem
        self.qchem_executable=None #str, Q-Chem executable to use
        self.use_perf=None #bool, should perf or time be used to monitor the Q-Chem run

class v40_qchem_payload(jsb.hook_base):

    def __init__(self,args):
        if not isinstance(args,v40_qchem_args):
            raise TypeError("args should be of type " + str(type(v40_qchem_args)))
        self.__qchem_args = args

    def generate(self,data,params,calc_env):
        """
        Generate shell script code from the queuing_system_data,
        the queuing_system_params and the calculation_environment
        provided
        """
        if not isinstance(data,qd.queuing_system_data):
            raise TypeError("data not of type qd.queuing_system_data")

        if not isinstance(params,qe.queuing_system_environment):
            raise TypeError("params not of type qe.queuing_system_environment")

        if not isinstance(calc_env,jsb.calculation_environment):
            raise TypeError("calc_env not of type calculation_environment")

        qchem_args = self.__qchem_args

        args=""
        if qchem_args.save_flag:
            args += " -save"
        if qchem_args.np_flag:
            args += " -np " + str(data.no_procs())
        if qchem_args.nt_flag:
            args += " -nt " + str(data.no_procs())
        args += ' "' + qchem_args.infile + '"'
        if qchem_args.outfile is not None:
            args += ' "' + qchem_args.outfile + '"'
        if qchem_args.savedir is not None:
            args += ' "' + qchem_args.savedir + '"'


        # Test if QCAUX and QC exist

        string = 'export QCSCRATCH="$' + calc_env.node_scratch_dir + '"\n'

        if qchem_args.use_perf:
            string += "if which perf &> /dev/null; then\n"
            string += "    perf " + qchem_args.qchem_executable + args + '\n'
            string += "    "+ calc_env.return_value + '=$?\n'
            string += "else\n"
            string += "    /usr/bin/time -v " + qchem_args.qchem_executable + args + '\n'
            string += "    "+ calc_env.return_value + '=$?\n'
            string += "fi\n"
        else:
            string += qchem_args.qchem_executable + args + '\n'
            string += calc_env.return_value + '=$?\n'
        string += "\n"

        string += "# check if job terminated successfully\n" \
                + 'if ! grep -q "Thank you very much for using Q-Chem.  Have a nice day." "' \
                + qchem_args.outfile + '"; then\n' \
                + '    ' + calc_env.return_value +'=1\n' \
                + 'fi\n'

        if qchem_args.savedir is not None:
            string += "\necho\n"
            string += "echo ------------------------------------------------------\n"
            string += "echo\n\n"

            string += 'echo "Files in $QCSCRATCH/'+qchem_args.savedir+ ': \n'
            string += '(\n'
            string += '    cd "$QCSCRATCH/' +qchem_args.savedir+ '"\n'
            string += "    ls -l | sed 's/^/    /g' \n"
            string += ')\n'

        return string

class v40(jsb.jobscript_builder):
    """
    Class to build a job script for q-chem 4.0
    """

    def __init__(self,qsys):
        super().__init__(qsys)
        self.__files_copy_in=None  # files that should be copied into the workdir
        self.__files_copy_out=None  # files that should be copied out of the workdir on successful execution
        self.__files_copy_error_out=None # files that should be copied out of the workdir on 
        self.__qchem_args=None

    @property
    def qchem_args(self):
        return self.__qchem_args

    @qchem_args.setter
    def qchem_args(self,val):
        if not isinstance(val,v40_qchem_args):
            raise TypeError("val should be of type " + str(type(v40_qchem_args)))
        self.__qchem_args = val

    def add_entries_to_argparse(self,argparse):
        """
        Adds required entries to an argparse Object supplied
        """
        super().add_entries_to_argparse(argparse)

        argparse.add_argument("infile",metavar="infile.in", type=str, help="The path to the Q-Chem input file")
        argparse.add_argument("--out",metavar="file",default=None,type=str, help="Q-Chem Output filename (Default: infile + \".out\")")
        argparse.add_argument("--save",default=False, action='store_true', help="Pass the -save option to qchem.")
        argparse.add_argument("--savedir", metavar="dir", default=None, type=str, help="The directory to use as the qchem savedir")
        argparse.add_argument("--np-to-qchem", default=False,action='store_true',help="Pass the -np option followed by the number of processors to qchem (MPI runs).")
        argparse.add_argument("--nt-to-qchem", default=False,action='store_true',help="Pass the -nt option followed by the number of processors to qchem (MP runs).")
        argparse.add_argument("--version", default=None, type=str, help="Version string identifying the Q-Chem version to be used.")
        argparse.add_argument("--perf", default=False, action='store_true',help="Use time or perf to montitor the memory/cpu usage of Q-Chem.")

        epilog="The script tries to complete parameters and information which are not explicitly provided on the commandline using the infile.in input file. This includes: " \
                + "jobname (Name of the file), output file name, walltime (via \"!QSYS wt=\" directive), number of processors (using threads directive or \"!QSYS np=\", " \
                + "physical and virtual memory (using memstatic and memtotal)"

        if argparse.epilog is None:
            argparse.epilog = epilog
        else:
            argparse.epilog += ("\n" + epilog)

    def _add_default_copy_out_files(self):
        pass
        # self.__files_copy_out.append("")
        # TODO Ideas for files to copy out:
        # Test.FChk
        # plot.attach.alpha
        # plot.detach.alpha
        # plot.attach.beta
        # plot.detach.beta
        # plot.attach.rlx.alpha
        # plot.detach.rlx.alpha
        # plot.attach.rlx.beta
        # plot.detach.rlx.beta
        # plot.trans
        # plot.hf
        # plot.mo
        # AIMD (directory)

    def _parse_infile(self,infile):
        """
        Update the inner data using the infile provided. If the values conflict, the
        values are left unchanged.
        """
        from argparse import ArgumentParser
        data = self.queuing_system_data


        section=None # the section we are currently in
        with open(infile,'r') as f:
            for line in f:
                line = line.strip()

                if line.startswith("!QSYS wt="):
                    if data.walltime is None:
                        try:
                            data.walltime = utils.interpret_string_as_time_interval(line[9:].strip())
                        except ArgumentParser:
                            pass
                        continue
                    else:
                        print("Warning: Ignoring walltime specified in input file via \"!QSYS wt=\", since walltime already given on commandline.")

                if line.startswith("!QSYS np="):
                    if data.no_nodes() == 0:
                        try:
                            node = qd.node_type()
                            node.no_procs = utils.interpret_string_as_time_interval(line[9:].strip())
                            data.add_node_type(node)
                        except ArgumentParser:
                            pass
                        continue
                    else:
                        print("Warning: Ignoring number of processes specified in input file via \"!QSYS np=\", since already specified on commandline.")

                if line.startswith("$end"):
                    section=None
                    continue

                if section is None:
                    if line.startswith("$molecule"):
                        section="molecule"
                        continue

                    if line.startswith("$rem"):
                        section="rem"
                        continue
                
                elif section == "molecule":
                    if line.startswith("READ"):
                        line = line[4:].strip()
                        self.__files_copy_in.append(line)
                    continue

                elif section == "rem":
                    if line.startswith("threads"):
                        line = line[7:].strip()

                        no=0
                        try:
                            no = int(line)
                        except ValueError:
                            continue

                        if data.no_nodes() < no:
                            node = qd.node_type()
                            node.no_procs = no - data.no_nodes()
                            data.add_node_type(node)

                        continue

                    if line.startswith("mem_total"):
                        # memory in mb
                        line = line[9:].strip()
                        
                        no=0
                        try:
                            no = int(line)
                        except ValueError:
                            continue

                        if data.physical_memory is None:
                            data.physical_memory = no*1024*1024 #value is in MB
                        if data.virtual_memory is None:
                            data.virtual_memory = no*1024*1024 #value is in MB
                        continue
                # end if
            # end for 

    def examine_args(self,args):
        """
        Update the inner data using the argparse data
        i.e. if there are conflicting values, the commandline takes
        preference

        If we find a flag to parse extra commandline args (-q, --qsys-args)
        invoke parsing of those arguments as well. Note that these explicitly
        provided arguments overwrite everything else on the commandline
        """
        super().examine_args(args)

        # check parsed data for consistency
        if not os.path.isfile(args.infile):
            raise SystemExit("File not found: " + args.infile)

        if args.save and args.savedir is None:
            raise SystemExit("If --save is provided a --savedir has to be set")

        if  args.savedir is not None and args.savedir.count("/") > 0:
            raise SystemExit("The savedir given should not be a path, just a name")

        # set internal values:
        self.__qchem_args = v40_qchem_args()
        self.__qchem_args.infile=args.infile
        self.__qchem_args.save_flag=args.save
        self.__qchem_args.savedir = args.savedir
        self.__qchem_args.np_flag=args.np_to_qchem
        self.__qchem_args.nt_flag=args.nt_to_qchem
        self.__qchem_args.use_perf = args.perf

        if args.version is not None:
            try:
                self.__qchem_args.qchem_executable = determine_qchem_path(version_string=args.version)
            except QChemPathNotDeterminedError as e:
                raise SystemExit("Invalid Q-Chem version string passed via --version")

        # split .in extension from filename
        filename, extension =  os.path.splitext(self.__qchem_args.infile)
        if extension != "in":
            filename = self.__qchem_args.infile

        # set outfile if not provided:
        if args.out is None:
            self.__qchem_args.outfile= filename + ".out"
        else:
            self.__qchem_args.outfile=args.out

        # set jobname if not yet set:
        if self.queuing_system_data.job_name is None:
            self.queuing_system_data.job_name = filename
        
        # files to copy in or out
        self.__files_copy_in =[]
        self.__files_copy_in.append(self.__qchem_args.infile)

        self.__files_copy_out=[]
        self._add_default_copy_out_files()

        self.__files_copy_error_out=[]
        self.__files_copy_error_out.append(self.__qchem_args.outfile)

        # parse infile 
        self._parse_infile(self.__qchem_args.infile)

        if self.__qchem_args.outfile is not None:
            self.__files_copy_out.append(self.__qchem_args.outfile)

    def build_script(self):
        if self.__qchem_args.qchem_executable is None:
            raise jsb.DataNotReady("No path to a Q-Chem wrapper script provided.")

        if self.__qchem_args.outfile is None:
            raise jsb.DataNotReady("No outputfile provided")
        
        if self.__qchem_args.save_flag and self.__qchem_args.savedir is None:
            raise jsb.DataNotReady("If save_flag is set, we need a savedir as well")

        self.add_payload_hook(jsb.copy_in_hook(self.__files_copy_in),-1000)
        self.add_payload_hook(v40_qchem_payload(self.__qchem_args))
        self.add_payload_hook(jsb.copy_out_hook(self.__files_copy_out),1000)

        self.add_error_hook(jsb.copy_out_hook(self.__files_copy_error_out),-1000)

        return super().build_script()



