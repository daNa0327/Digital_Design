open_vcd dump.vcd
log_vcd [get_objects -r /*]
run all
close_vcd
quit