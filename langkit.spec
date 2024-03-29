# The test suite isn't normally run. It can be enabled with "--with=check".
%bcond_with check

# Upstream source information.
%global upstream_owner    AdaCore
%global upstream_name     langkit
%global upstream_version  24.0.0
%global upstream_gittag   v%{upstream_version}

Name:           langkit
Version:        %{upstream_version}
Release:        1%{?dist}
Summary:        A language creation framework

License:        Apache-2.0 WITH LLVM-Exception

URL:            https://github.com/%{upstream_owner}/%{upstream_name}
Source:         %{url}/archive/%{upstream_gittag}/%{upstream_name}-%{upstream_version}.tar.gz

# [Fedora-specific] Set support library soname.
Patch:          %{name}-set-soname-of-support-library.patch
# [Fedora-specific] All builds during testing (check) should be of type `relocatable`.
Patch:          %{name}-no-static-test-builds.patch
# [Fedora-specific] Skip style checks when testing: not relevant for functioning.
Patch:          %{name}-skip-style-checks.patch
# [Fedora-specific] Generation of standalone code not supported: no bundling.
Patch:          %{name}-generation-of-standalone-code-not-supported.patch
# Python 3.12: Fix syntax warning on incorrect usage of the escape character.
Patch:          %{name}-fix-incorrect-usage-of-escape-character.patch
# Add missing dependency to the railroad-diagrams PyPI package.
Patch:          %{name}-add-railroad-dependency.patch

BuildRequires:  gcc-gnat gprbuild make sed
# A fedora-gnat-project-common that contains GPRbuild_flags is needed.
BuildRequires:  fedora-gnat-project-common >= 3.17
BuildRequires:  gnatcoll-core-devel
BuildRequires:  gnatcoll-gmp-devel
BuildRequires:  gnatcoll-iconv-devel
BuildRequires:  libadasat-devel
BuildRequires:  python3-devel
%if %{with check}
BuildRequires:  python3-e3-testsuite
BuildRequires:  python3-pexpect
BuildRequires:  gdb
%endif
BuildRequires:  python3-sphinx
BuildRequires:  python3-sphinx_rtd_theme

# Build only on architectures where GPRbuild is available.
ExclusiveArch:  %{GPRbuild_arches}

%global common_description_en \
Langkit is a tool whose purpose is to ease the development of libraries \
to analyze program source files. It makes it super-easy to create combined \
lexers, parsers and semantic analyzers as libraries that have C, Ada and \
Python bindings.}

%description %{common_description_en}


#################
## Subpackages ##
#################

%package devel
Summary:    A language creation framework
Requires:   %{name}-support%{?_isa} = %{version}-%{release}
Requires:   fedora-gnat-project-common
Requires:   gnatcoll-core-devel
Requires:   gnatcoll-gmp-devel
Requires:   gnatcoll-iconv-devel
Requires:   libadasat-devel
# An additional provides to help users find the package.
Provides:   python3-%{name}

%description devel %{common_description_en}


%package support
Summary:    Runtime support for Langkit-generated libraries

%description support %{common_description_en}

This package contains the runtime support library.


#############
## Prepare ##
#############

%prep
%autosetup -p1


############################
## Generate BuildRequires ##
############################

%generate_buildrequires
%pyproject_buildrequires


###########
## Build ##
###########

%build

# Build framework.
%pyproject_wheel

# Build the support library.
gprbuild %{GPRbuild_flags} \
         -XBUILD_MODE=prod -XLIBRARY_TYPE=relocatable -XVERSION=%{version} \
         -P langkit/support/langkit_support.gpr


#############
## Install ##
#############

%install

# Install framework.
%pyproject_install
%pyproject_save_files langkit

# Install the support library.
gprinstall --create-missing-dirs --no-manifest --no-build-var \
           --prefix=%{buildroot}%{_prefix} \
           --ali-subdir=%{buildroot}%{_libdir}/langkit-support \
           --lib-subdir=%{buildroot}%{_libdir} \
           --link-lib-subdir=%{buildroot}%{_libdir} \
           --sources-subdir=%{buildroot}%{_includedir}/langkit-support \
           -XBUILD_MODE=prod -XLIBRARY_TYPE=relocatable -XVERSION=%{version} \
           -P langkit/support/langkit_support.gpr

# Fix up some things that GPRinstall does wrong.
ln --symbolic --force lib%{name}_support.so.%{version} %{buildroot}%{_libdir}/lib%{name}_support.so
ls -l %{buildroot}%{_libdir}

# Make the generated usage project file architecture-independent.
sed --regexp-extended --in-place \
    '--expression=1i with "directories";' \
    '--expression=/^--  This project has been generated/d' \
    '--expression=s|^( *for +Source_Dirs +use +).*;$|\1(Directories.Includedir \& "/langkit-support");|i' \
    '--expression=s|^( *for +Library_Dir +use +).*;$|\1Directories.Libdir;|i' \
    '--expression=s|^( *for +Library_ALI_Dir +use +).*;$|\1Directories.Libdir \& "/langkit-support";|i' \
    %{buildroot}%{_GNAT_project_dir}/langkit_support.gpr
# The Sed commands are:
# 1: Insert a with clause before the first line to import the directories
#    project.
# 2: Delete a comment that mentions the architecture.
# 3: Replace the value of Source_Dirs with a pathname based on
#    Directories.Includedir.
# 4: Replace the value of Library_Dir with Directories.Libdir.
# 5: Replace the value of Library_ALI_Dir with a pathname based on
#    Directories.Libdir.


###########
## Check ##
###########

%if %{with check}
%check

# Create an override for directories.gpr.
mkdir multilib
cat << EOF > ./multilib/directories.gpr
abstract project Directories is
   Libdir     := "%{buildroot}%{_libdir}";
   Includedir := "%{buildroot}%{_includedir}";
end Directories;
EOF

# Make the files installed in the buildroot visible to the testsuite.
export PATH=%{buildroot}%{_bindir}:$PATH
export LD_LIBRARY_PATH=%{buildroot}%{_libdir}:$LD_LIBRARY_PATH
export GPR_PROJECT_PATH=${PWD}/multilib:%{buildroot}%{_GNAT_project_dir}:$GPR_PROJECT_PATH
export PYTHONPATH=%{buildroot}%{python3_sitearch}:%{buildroot}%{python3_sitelib}:$PYTHONPATH

# Build the test libraries. We don't use `manage.py make` as we want to use
# the Fedora build flags and make the tools position independent (as is
# recommended for Fedora).
for lang in lkt python; do

    pushd . && cd ./contrib/$lang

    # Generate the source code.
    # -- ignore undocumented nodes, following `manage.py make`.
    %python3 ./manage.py generate --disable-warning=undocumented-nodes

    # Build the library. Use extensions and the latest Ada version (-gnatX).
    gprbuild %{GPRbuild_flags} -cargs:Ada -gnatX -gargs \
             -XBUILD_MODE=prod -XLIBRARY_TYPE=relocatable \
             build/lib${lang}lang.gpr

    # Additional flags to make the executables (tools) position independent
    # and make the executables link dynamically with the GNAT runtime.
    %global GPRbuild_flags_pie -cargs -fPIC -largs -pie -bargs -shared -gargs

    # Build the tools.
    gprbuild %{GPRbuild_flags} %{GPRbuild_flags_pie} -largs -L./lib -gargs \
             -XBUILD_MODE=prod -XLIBRARY_TYPE=relocatable \
             build/mains.gpr

    popd

done

# Setup the environment. Skip langkit support because we already added it
# to the environment at the beginning of the check section.
eval $(%python3 ./manage.py setenv --no-langkit-support --build-mode=prod)

# Run the tests.
%python3 testsuite/testsuite.py \
         --show-error-output \
         --max-consecutive-failures=4 \
         --with-python=%python3 \
         --disable-tear-up-builds \
         --disable-ocaml \
         --disable-java

%endif


###########
## Files ##
###########

%files devel -f %pyproject_files
%license LICENSE.txt
%doc README*
%{_bindir}/create-project.py

# Development files for the support library.
%{_GNAT_project_dir}/%{name}_support.gpr
%{_includedir}/%{name}-support
%dir %{_libdir}/%{name}-support
%attr(444,-,-) %{_libdir}/%{name}-support/*.ali
%{_libdir}/lib%{name}_support.so


%files support
%{_libdir}/lib%{name}_support.so.%{version}


###############
## Changelog ##
###############

%changelog
* Sun Jan 28 2024 Dennis van Raaij <dvraaij@fedoraproject.org> - 24.0.0-1
- Updated to v24.0.0.
- Updated license: LLVM exception has been added.
- Removed langkit-getargspec-is-deprecated.patch; has been fixed upstream (commit: 52084ad).
- Removed langkit-suppress-null-range-warning.patch; no longer needed.
- Added 'libadasat' as build dependency.

* Sun Oct 30 2022 Dennis van Raaij <dvraaij@fedoraproject.org> - 23.0.0-1
- Updated to v23.0.0.
- Removed langkit-collections-sequence.patch; has been fixed upstream (commit: cdc5768).

* Sun Sep 04 2022 Dennis van Raaij <dvraaij@fedoraproject.org> - 22.0.0-1
- New package.
