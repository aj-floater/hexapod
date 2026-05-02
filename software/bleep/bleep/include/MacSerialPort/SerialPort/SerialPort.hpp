//SerialPort.hpp

#ifndef __SERIAL_PORT_HPP__
#define __SERIAL_PORT_HPP__


#include <unistd.h> //ssize_t

#include <cstdio>
#include <iostream>
#include <array>


int openAndConfigureSerialPort(const char* portPath, int baudRate);



bool serialPortIsOpen();



ssize_t flushSerialData();



ssize_t writeSerialData(const char* bytes, size_t length);



ssize_t readSerialData(char* bytes, size_t length);



ssize_t closeSerialPort(void);



int getSerialFileDescriptor(void);



std::string getSerialPorts();

std::vector<std::string> parseSerialPorts(const std::string& output);

#endif //__SERIAL_PORT_HPP__