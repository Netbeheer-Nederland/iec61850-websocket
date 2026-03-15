# FT4: Send setpoints to the Connected Party by using Control and SetDataValues services

The following negative test case variations can be considered (Optional):

- Send a GetDataValues request to a non-existing data object- Send a Operate request with a value of a wrong type- Send
                                                                                                                   a
                                                                                                                   Operate
                                                                                                                   request
                                                                                                                   to a
                                                                                                                   setting
                                                                                                                   data
                                                                                                                   object (
                                                                                                                   ASG)-
Send a SetDataValues request to a non-existing data object- Send a SetDataValues request with a value of a wrong type-
Send a Operate request with an out-of-range value

**Conclusion:**

- It is possible to set values to Oper items using Operate command
- For non-operate items, setDataValues can be used for setting values to data objects or data attributes
- Operate command only works after Select
- Operate command only works after for data objects with data attribute with functional constraint “CO”
- If a value is out of range in an operate function, the service error “invalid position” is returned
- The test case **passed.**
